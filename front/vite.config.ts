import { fileURLToPath, URL } from 'node:url'
import type { ClientRequest, IncomingMessage } from 'node:http'
import vue from '@vitejs/plugin-vue'
import { defineConfig, type Plugin } from 'vite'


function realClientIpPlugin(): Plugin {
  /**
   * 在 Vite 代理读取请求头之前，用实际 TCP 对端覆盖浏览器可伪造的转发地址。
   * 返回：供 Vite 开发服务器加载的本地插件。
   * 副作用：所有进入开发服务器的请求只保留实际连接来源作为 X-Forwarded-For。
   */
  return {
    name: 'platform-real-client-ip',
    configureServer(server) {
      server.middlewares.use((request, _response, next) => {
        const clientIp = request.socket.remoteAddress || ''
        if (clientIp) request.headers['x-forwarded-for'] = clientIp
        else delete request.headers['x-forwarded-for']
        next()
      })
    },
  }
}


function forwardRealClientIp(proxyRequest: ClientRequest, request: IncomingMessage) {
  /**
   * 使用 Vite 实际 TCP 对端覆盖客户端可伪造的转发地址。
   * 参数：`proxyRequest` 为发往后端的代理请求；`request` 为浏览器连接到 Vite 的原始请求。
   * 返回：无显式返回值。
   * 副作用：覆盖发往本机后端的 X-Forwarded-For 请求头。
   */
  const clientIp = request.socket.remoteAddress || ''
  if (clientIp) {
    request.headers['x-forwarded-for'] = clientIp
    proxyRequest.setHeader('X-Forwarded-For', clientIp)
  }
  else {
    delete request.headers['x-forwarded-for']
    proxyRequest.removeHeader('X-Forwarded-For')
  }
}


export default defineConfig({
  plugins: [realClientIpPlugin(), vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://192.168.1.12:8001',
        changeOrigin: true,
        xfwd: false,
        configure(proxy) {
          proxy.on('proxyReq', forwardRealClientIp)
        },
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts'],
        },
      },
    },
  },
})
