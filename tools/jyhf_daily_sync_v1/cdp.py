"""Read-only application data acquisition through the user's authorized JYHF renderer.
Only normal App UI and API responses triggered by visible row selection; never access credentials."""
from __future__ import annotations
import json
import time
from urllib.request import urlopen
from urllib.parse import urlparse,parse_qs
import websocket
from .model import SyncContractError,validate_quote,validate_first_level_branches

class AppSession:
    def __init__(self, port=9223):
        try:
            with urlopen(f'http://127.0.0.1:{port}/json/list',timeout=5) as response:
                tabs=json.load(response)
            found=[p for p in tabs if p.get('type')=='page' and '久赢恒丰' in p.get('title','')]
            if len(found)!=1:raise SyncContractError('app_renderer_unavailable')
            self.ws=websocket.create_connection(found[0]['webSocketDebuggerUrl'],timeout=1.2)
        except SyncContractError:raise
        except Exception as e:raise SyncContractError('app_cdp_connection_failed') from e
        self.seq=0
        self.network={}
        self.original_selection=None
        self._call('Network.enable',{})
    def close(self):
        self.ws.close()
    def _send(self,method,params):
        self.seq+=1
        self.ws.send(json.dumps({'id':self.seq,'method':method,'params':params}))
        return self.seq
    def _consume(self,message):
        method=message.get('method');p=message.get('params',{})
        if method=='Network.requestWillBeSent':
            u=p.get('request',{}).get('url','')
            if '/api/app/' in u:
                parsed=urlparse(u)
                ep=parsed.path.split('/api/app/',1)[-1]
                self.network[p['requestId']]={'endpoint':ep,'params':parse_qs(parsed.query),'url':u,
                                                'method':p.get('request',{}).get('method')}
        elif method=='Network.responseReceived':
            if p.get('requestId') in self.network:
                self.network[p['requestId']]['http_status']=p.get('response',{}).get('status')
        elif method=='Network.loadingFinished':
            if p.get('requestId') in self.network:
                self.network[p['requestId']]['finished']=True
    def _wait(self,mid,seconds=12):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:msg=json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:continue
            self._consume(msg)
            if msg.get('id')==mid:
                if msg.get('error') or msg.get('result',{}).get('exceptionDetails'):
                    raise SyncContractError('cdp_evaluation_failed')
                return msg.get('result',{}).get('result',{}).get('value',msg.get('result',{}))
        raise SyncContractError('cdp_call_timeout')
    def _call(self,method,params,seconds=12):
        mid=self._send(method,params)
        return self._wait(mid,seconds)
    def js(self,expression,seconds=15):
        return self._call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True},seconds)
    def _drain(self,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:msg=json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:continue
            self._consume(msg)
    def read_list(self):
        # Do not hijack any other App route. Refresh this page via native navigation.
        pre=self.js("""(()=>({route:document.querySelector('#app')?.__vue_app__?.config.globalProperties?.$router?.currentRoute.value.fullPath||'',title:document.title}))()""")
        if pre.get('route')!='/subject/all':raise SyncContractError('app_not_on_subject_all_page')
        # Preserve the user's current selected theme before programmatic cycling.
        current=self.js("""(()=>{let s=new Set(),ts=[];function f(v){if(!v||s.has(v))return;s.add(v);
        let c=v.component;if(c){if(c.type?.name==='VxeTable')ts.push(c);f(c.subTree)}
        if(Array.isArray(v.children))v.children.forEach(f);if(v.suspense)f(v.suspense.activeBranch)}
        f(document.querySelector('#app')?._vnode);
        let t=ts.find(x=>(x.proxy?.getTableData?.()?.fullData?.length||0)>100);
        return t?.proxy?.getCurrentRecord?.()?.subjectId||null})()""")
        self.original_selection=str(current) if current is not None else None
        self.network.clear()
        refresh="""(async()=>{let seen=new Set(),tables=[];function f(v){if(!v||seen.has(v))return;seen.add(v);
let c=v.component;if(c){if(c.type?.name==='VxeTable')tables.push(c);f(c.subTree)}
if(Array.isArray(v.children))v.children.forEach(f);if(v.suspense)f(v.suspense.activeBranch)}
f(document.querySelector('#app')?._vnode);
let t=tables.find(x=>(x.proxy?.getTableData?.()?.fullData?.length||0)>100);
let handler=t?.vnode?.props?.onSortChange;if(typeof handler!=='function')return 'no_native_refresh_handler';
handler({field:'pctChg',order:'desc'});
await new Promise(x=>setTimeout(x,1600));
return document.querySelector('#app')?.__vue_app__?.config.globalProperties?.$router?.currentRoute.value.fullPath})()"""
        if self.js(refresh,seconds=15)!='/subject/all':
            raise SyncContractError('app_native_list_refresh_failed')
        self._drain(0.4)
        live=[m for m in self.network.values() if m['endpoint']=='subject/list/v2'
              and m.get('http_status')==200 and m.get('finished')]
        if not live:raise SyncContractError('no_fresh_app_list_http_200')
        expr="""(()=>{let seen=new Set(),found=[];function f(v){if(!v||seen.has(v)||seen.size>18000)return;seen.add(v);
let c=v.component;if(c){if(c.type?.name==='VxeTable'){let t=c.proxy?.getTableData?.()?.fullData||c.props?.data||[];
if(Array.isArray(t)&&t.length>100)found.push(t)}f(c.subTree)}
if(Array.isArray(v.children))v.children.forEach(f);if(v.suspense)f(v.suspense.activeBranch)}
f(document.querySelector('#app')?._vnode);
if(found.length!==1)return null;
let names=['subjectId','subjectName','pctChg','leadStockId','leadStockName','hasChild'];
return found[0].map(r=>{let x={};for(let k of names)x[k]=r[k]??null;return x})})()"""
        data=self.js(expr,seconds=15)
        if not isinstance(data,list) or len(data)<100:raise SyncContractError('app_list_empty_or_truncated')
        return data
    def read_stock(self,subject_id,name,trade_date):
        # request originates only through a real normal table row selection.
        self.network.clear()
        js="""(async()=>{let id=%s,name=%s;let seen=new Set(),tables=[];function visit(v){if(!v||seen.has(v)||seen.size>16000)return;
seen.add(v);let c=v.component;if(c){if(c.type?.name==='VxeTable')tables.push(c);visit(c.subTree)}
if(Array.isArray(v.children))v.children.forEach(visit);if(v.suspense)visit(v.suspense.activeBranch)}
visit(document.querySelector('#app')?._vnode);
let main=tables.find(c=>(c.proxy?.getTableData?.()?.fullData?.length||0)>100);
let row=main?.proxy?.getTableData?.()?.fullData?.find(x=>String(x.subjectId)===id);
if(!row||row.subjectName!==name||typeof main?.vnode?.props?.onCurrentChange!=='function')return {error:'row_not_found'};
// Always toggle to a different row before selecting the target: selecting the
// currently-selected row does not necessarily trigger a new network request.
let alt=main.proxy?.getTableData?.()?.fullData?.find(x=>String(x.subjectId)!==id);
if(!alt)return {error:'no_alternative_row_to_force_new_request'};
main.vnode.props.onCurrentChange({row:alt});if(main.proxy?.setCurrentRow)await main.proxy.setCurrentRow(alt);
await new Promise(x=>setTimeout(x,650));
main.vnode.props.onCurrentChange({row});if(main.proxy?.setCurrentRow)await main.proxy.setCurrentRow(row);
await new Promise(x=>setTimeout(x,1600));
seen=new Set();tables=[];visit(document.querySelector('#app')?._vnode);
let raw=tables.find(c=>Array.isArray(c.props?.data)&&Array.isArray(c.props.data[0]))?.props?.data||[];
return {visible_codes:raw.map(x=>String(x[2])),visible_count:raw.length}})()""" % (json.dumps(subject_id),json.dumps(name,ensure_ascii=False))
        v=self.js(js,seconds=15)
        if not isinstance(v,dict) or v.get('error'):raise SyncContractError('app_stock_table_not_loaded')
        self._drain(0.3)
        requests=[(rid,r) for rid,r in self.network.items() if r['endpoint']=='stock/realtime-by-subject/v2'
                  and subject_id in r.get('params',{}).get('subjectId',[]) and r.get('http_status')==200]
        if len(requests)!=1:
            statuses=[(r['endpoint'],r['params'].get('subjectId'),r.get('http_status'),r.get('finished')) for r in self.network.values()
                      if r['endpoint']=='stock/realtime-by-subject/v2']
            raise SyncContractError('stock_request_not_unique_or_failed:'+str(statuses[:10]))
        rid,r=requests[0]
        if not r.get('finished'):self._drain(1.0)
        if not r.get('finished'):raise SyncContractError('stock_request_incomplete')
        body=self._call('Network.getResponseBody',{'requestId':rid},seconds=9)
        if not isinstance(body,dict) or body.get('base64Encoded'):
            raise SyncContractError('stock_response_body_unavailable')
        try:obj=json.loads(body['body'])
        except (KeyError,ValueError,TypeError):raise SyncContractError('stock_response_not_json') from None
        if not isinstance(obj,dict) or not isinstance(obj.get('rows'),list):
            raise SyncContractError('stock_response_wrong_shape')
        return validate_quote(subject_id,name,trade_date,obj['rows'],obj.get('code'),obj.get('total'),v['visible_codes'])
    def read_branches(self,subject_id,name):
        expr="""(async()=>{let id=%s,name=%s;let r=document.querySelector('#app')?.__vue_app__?.config.globalProperties?.$router;
if(!r||r.currentRoute.value.fullPath!='/subject/all')return {error:'route_incorrect'};
await r.push('/subject/detail/'+id);let root='',kids=[];
for(let i=0;i<20;i++){await new Promise(x=>setTimeout(x,220));
root=(document.querySelector('.tree-table-td1-1 .s-name')?.innerText||'').trim();
kids=Array.from(document.querySelectorAll('.tree-table-td1-2 .s-name')).map(x=>(x.innerText||'').trim()).filter(Boolean);
if(root===name&&kids.length)break;}
await r.push('/subject/all');await new Promise(x=>setTimeout(x,650));
return {root,branches:kids,return_route:r.currentRoute.value.fullPath}})()""" % (json.dumps(subject_id),json.dumps(name,ensure_ascii=False))
        val=self.js(expr,seconds=18)
        if not isinstance(val,dict) or val.get('return_route')!='/subject/all':
            raise SyncContractError('app_branch_route_not_restored')
        # Root visible but no children is a valid observed condition.
        return validate_first_level_branches(name,val.get('root'),val.get('branches'))

    def restore_selection(self):
        if self.original_selection is None:return None
        js="""(async()=>{const id=%s;let r=document.querySelector('#app')?.__vue_app__?.config.globalProperties?.$router;
if(!r)return {error:'missing_router'};if(r.currentRoute.value.fullPath!='/subject/all')await r.push('/subject/all');
let s=new Set(),ts=[];function f(v){if(!v||s.has(v))return;s.add(v);let c=v.component;
if(c){if(c.type?.name==='VxeTable')ts.push(c);f(c.subTree)}
if(Array.isArray(v.children))v.children.forEach(f);if(v.suspense)f(v.suspense.activeBranch)}
f(document.querySelector('#app')?._vnode);
let t=ts.find(x=>(x.proxy?.getTableData?.()?.fullData?.length||0)>100);
let row=t?.proxy?.getTableData?.()?.fullData?.find(v=>String(v.subjectId)===id);
if(row){t.vnode?.props?.onCurrentChange?.({row});if(t.proxy?.setCurrentRow)await t.proxy.setCurrentRow(row)}
return {restored:!!row,route:r.currentRoute.value.fullPath}})()""" % json.dumps(self.original_selection)
        return self.js(js,seconds=15)
