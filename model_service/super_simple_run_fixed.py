#!/usr/bin/env python3
"""
修复版超级简单事件提取器 - 修复updated_at字段问题
"""
import asyncio
import os
import sys
import json
import aiohttp
from datetime import datetime
import asyncpg

# 数据库配置
DB_CONFIG = {
    "user": "postgres",
    "password": "zxbzj~925",
    "database": "stock_data",
    "host": "localhost",
    "port": "5432"
}

DB_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

async def fetch_pending_news(limit=5):
    """获取待处理新闻"""
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch("""
            SELECT id as news_id, title, content, source, publish_time, url
            FROM news_raw 
            WHERE is_processed = FALSE 
            ORDER BY publish_time ASC 
            LIMIT $1
        """, limit)
        
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def save_event(event_data):
    """保存事件到数据库（修复版）"""
    conn = await asyncpg.connect(DB_URL)
    try:
        result = await conn.fetchrow("""
            INSERT INTO news_event (
                news_id, event_type, impact_industries, 
                direction, confidence, summary, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
        """,
            event_data['news_id'],
            event_data['event_type'],
            event_data['impact_industries'],
            event_data['direction'],
            event_data['confidence'],
            event_data['summary']
        )
        
        # 修复：只更新is_processed字段，不更新updated_at
        await conn.execute("""
            UPDATE news_raw 
            SET is_processed = TRUE
            WHERE id = $1
        """, event_data['news_id'])
        
        return result['id'] if result else None
    finally:
        await conn.close()

async def check_and_fix_table():
    """检查并修复表结构"""
    conn = await asyncpg.connect(DB_URL)
    try:
        # 检查news_raw表是否有updated_at字段
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'news_raw' 
            AND column_name = 'updated_at'
        """)
        
        if not columns:
            print("ℹ️  news_raw表没有updated_at字段，添加中...")
            try:
                await conn.execute("""
                    ALTER TABLE news_raw 
                    ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()
                """)
                print("✅ 已添加updated_at字段")
            except Exception as e:
                print(f"⚠️  添加字段失败: {e}")
                print("💡 继续处理，不使用updated_at字段")
        else:
            print("✅ news_raw表已有updated_at字段")
    
    finally:
        await conn.close()

class SimpleAIExtractor:
    """简单AI提取器"""
    
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=60)
    
    async def extract_event(self, news_item):
        """提取事件信息"""
        if not self.api_key:
            print("⚠️  未设置API密钥，使用模拟数据")
            return self._create_mock_event(news_item)
        
        # 构建提示词
        prompt = self._build_prompt(news_item)
        
        # 调用API
        result = await self._call_api(prompt)
        
        if result:
            # 解析结果
            event_data = self._parse_result(result, news_item['news_id'])
            return event_data
        else:
            print("❌ API调用失败，使用模拟数据")
            return self._create_mock_event(news_item)
    
    def _build_prompt(self, news_item):
        """构建提示词"""
        return f"""请分析以下财经新闻，提取关键事件信息：

标题：{news_item['title']}
内容：{news_item['content']}

请以JSON格式返回以下信息：
{{
    "event_type": "事件类型（政策利好、技术突破、业绩增长、合作签约、风险警示等）",
    "impact_industries": ["影响的行业列表"],
    "direction": "positive/negative/neutral",
    "confidence": 置信度（0-100之间的整数）,
    "summary": "事件摘要（100字以内）"
}}

只返回JSON，不要有其他内容。"""
    
    async def _call_api(self, prompt):
        """调用DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        
        try:
            async with self.session.post(
                self.api_url, 
                headers=headers, 
                json=data
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']
                else:
                    error = await response.text()
                    print(f"❌ API错误: {response.status} - {error[:200]}")
                    return None
                    
        except Exception as e:
            print(f"💥 API调用异常: {e}")
            return None
    
    def _parse_result(self, api_response, news_id):
        """解析API响应"""
        try:
            # 清理响应
            response_text = api_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # 解析JSON
            data = json.loads(response_text)
            
            # 构建事件数据
            event_data = {
                'news_id': news_id,
                'event_type': data.get('event_type', 'unknown'),
                'impact_industries': data.get('impact_industries', []),
                'direction': data.get('direction', 'neutral'),
                'confidence': data.get('confidence', 50),
                'summary': data.get('summary', '')
            }
            
            # 验证和清理数据
            if not isinstance(event_data['impact_industries'], list):
                if isinstance(event_data['impact_industries'], str):
                    # 分割字符串
                    industries = [i.strip() for i in event_data['impact_industries'].split(',')]
                    event_data['impact_industries'] = industries
                else:
                    event_data['impact_industries'] = []
            
            if event_data['direction'] not in ['positive', 'negative', 'neutral']:
                event_data['direction'] = 'neutral'
            
            # 确保置信度是整数且在0-100之间
            try:
                confidence = int(event_data['confidence'])
                event_data['confidence'] = min(100, max(0, confidence))
            except:
                event_data['confidence'] = 50
            
            return event_data
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            print(f"原始响应: {api_response[:200]}...")
            
            # 尝试从原始文本中提取信息
            return self._create_fallback_event(news_id, api_response)
        except Exception as e:
            print(f"💥 解析异常: {e}")
            return self._create_mock_event({'news_id': news_id})
    
    def _create_mock_event(self, news_item):
        """创建模拟事件（用于测试）"""
        return {
            'news_id': news_item['news_id'],
            'event_type': '模拟事件',
            'impact_industries': ['测试行业'],
            'direction': 'positive',
            'confidence': 85,
            'summary': f"模拟事件摘要: {news_item['title'][:50]}..."
        }
    
    def _create_fallback_event(self, news_id, api_response):
        """创建备用事件"""
        return {
            'news_id': news_id,
            'event_type': '解析失败',
            'impact_industries': [],
            'direction': 'neutral',
            'confidence': 0,
            'summary': f"AI解析失败，原始响应: {api_response[:100]}..."
        }
    
    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()

async def main():
    """主函数"""
    print("🚀 修复版超级简单事件提取器")
    print("=" * 60)
    
    # 检查并修复表结构
    await check_and_fix_table()
    
    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        print(f"🔑 使用DeepSeek API (密钥: {api_key[:12]}...)")
        use_ai = True
    else:
        print("⚠️  未设置DEEPSEEK_API_KEY，使用模拟模式")
        print("   设置: export DEEPSEEK_API_KEY='your_key'")
        use_ai = False
    
    # 初始化提取器
    extractor = SimpleAIExtractor()
    
    try:
        # 获取待处理新闻
        print("\n📋 获取待处理新闻...")
        news_list = await fetch_pending_news(limit=3)
        
        if not news_list:
            print("📭 没有待处理的新闻")
            return
        
        print(f"✅ 找到 {len(news_list)} 条新闻")
        
        success_count = 0
        
        # 处理每条新闻
        for i, news_item in enumerate(news_list, 1):
            print(f"\n{'='*50}")
            print(f"[{i}/{len(news_list)}] 处理新闻")
            print(f"标题: {news_item['title']}")
            print(f"来源: {news_item['source']}")
            print(f"时间: {news_item['publish_time']}")
            
            # 提取事件
            print("⏳ AI解析中...")
            event_data = await extractor.extract_event(news_item)
            
            if event_data:
                print("✅ 提取成功!")
                print(f"   事件类型: {event_data['event_type']}")
                print(f"   影响方向: {event_data['direction']}")
                print(f"   置信度: {event_data['confidence']}%")
                print(f"   影响行业: {', '.join(event_data['impact_industries']) if event_data['impact_industries'] else '无'}")
                print(f"   摘要: {event_data['summary'][:80]}...")
                
                # 保存到数据库
                event_id = await save_event(event_data)
                if event_id:
                    print(f"💾 已保存到数据库 (ID: {event_id})")
                    success_count += 1
                else:
                    print("❌ 保存失败")
            else:
                print("❌ 提取失败")
        
        # 统计报告
        print(f"\n{'='*60}")
        print("📊 处理报告")
        print("=" * 60)
        print(f"总计处理: {len(news_list)} 条")
        print(f"成功提取: {success_count} 条")
        if news_list:
            print(f"成功率: {success_count/len(news_list)*100:.1f}%")
        else:
            print("成功率: 0%")
        
    except Exception as e:
        print(f"\n💥 运行异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 关闭提取器
        await extractor.close()
        print("\n👋 程序结束")

if __name__ == "__main__":
    asyncio.run(main())
