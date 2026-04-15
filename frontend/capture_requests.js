// 这个脚本可以捕获所有网络请求
if (typeof window !== 'undefined') {
    const originalFetch = window.fetch;
    const originalXHROpen = XMLHttpRequest.prototype.open;
    const originalXHRSend = XMLHttpRequest.prototype.send;
    const originalWS = window.WebSocket;
    
    const requests = [];
    
    // 拦截fetch
    window.fetch = function(...args) {
        const [url, options = {}] = args;
        const method = options.method || 'GET';
        requests.push({type: 'fetch', url, method, timestamp: Date.now()});
        
        console.log(`[FETCH] ${method} ${url}`);
        
        return originalFetch.apply(this, args).then(response => {
            if (response.status === 405) {
                console.error(`[405 ERROR] ${method} ${url}`, response);
            }
            return response;
        }).catch(error => {
            console.error(`[FETCH ERROR] ${method} ${url}`, error);
            throw error;
        });
    };
    
    // 拦截XMLHttpRequest
    XMLHttpRequest.prototype.open = function(method, url) {
        requests.push({type: 'xhr', url, method, timestamp: Date.now()});
        console.log(`[XHR] ${method} ${url}`);
        return originalXHROpen.apply(this, arguments);
    };
    
    // 拦截WebSocket
    if (originalWS) {
        window.WebSocket = function(url) {
            requests.push({type: 'websocket', url, timestamp: Date.now()});
            console.log(`[WebSocket] ${url}`);
            return new originalWS(url);
        };
    }
    
    // 暴露请求日志
    window.getRequestLogs = () => requests;
    
    console.log('网络请求拦截器已安装');
}
