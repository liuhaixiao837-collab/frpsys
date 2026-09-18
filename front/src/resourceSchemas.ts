export type FieldType = 'text' | 'textarea' | 'richtext' | 'number' | 'checkbox' | 'statusSwitch' | 'select' | 'multiselect' | 'json' | 'list' | 'password' | 'file'
export type ResourceColumn = string | [string, string]

export type ResourceField = {
  key: string
  label: string
  type?: FieldType
  required?: boolean
  options?: Array<[string | boolean, string]>
  optionEndpoint?: string
  optionLabel?: string
  optionValue?: string
  uploadEndpoint?: (item: any) => string
  fileField?: string
  placeholder?: string
  readonly?: boolean
  default?: any
}

export type ResourceAction = {
  label: string
  labelFor?: (item: any) => string
  permission?: string
  endpoint?: (item: any) => string
  navigateTo?: (item: any) => string
  templateEndpoint?: string | ((item: any) => string)
  templateLabel?: string
  method?: string
  body?: (item: any, selectedIds?: Array<string | number>) => any
  fields?: ResourceField[]
  upload?: boolean
  fileField?: string
  requiresSelection?: boolean
}

export type ResourceSchema = {
  title: string
  description: string
  endpoint: string
  idKey?: string
  readonly?: boolean
  selectable?: boolean
  compactTable?: boolean
  compactTableFill?: boolean
  fields: ResourceField[]
  columns: ResourceColumn[]
  searchPlaceholder?: string
  actions?: ResourceAction[]
  collectionActions?: ResourceAction[]
}

const statusOptions: Array<[string, string]> = [['enabled', '启用'], ['disabled', '停用'], ['active', '活跃'], ['mock', '模拟']]

export const resourceSchemas: Record<string, ResourceSchema> = {
  '/security/frp/servers': {
    title: 'FRP 服务端',
    description: '',
    endpoint: '/security/frp/servers/',
    compactTable: true,
    compactTableFill: true,
    searchPlaceholder: '搜索服务端名称、编码或公网地址',
    columns: [
      ['name', '服务端'],
      ['server_code', '编码'],
      ['public_host', '公网地址'],
      ['bind_port', '端口'],
      ['allow_ports', '允许端口'],
      ['agent_count', 'Agent'],
      ['status', '状态'],
      ['last_test_at', '最近测试'],
    ],
    fields: [
      { key: 'name', label: '服务端名称', required: true },
      { key: 'server_code', label: '服务端编码', required: true, placeholder: '例如 prod-frp-01' },
      { key: 'public_host', label: '公网地址', required: true, placeholder: 'frp.example.com 或 IP' },
      { key: 'bind_port', label: '服务端端口', type: 'number' },
      { key: 'allow_ports', label: '允许映射端口', placeholder: '例如 6000-6090，留空则同步 frps 后自动填充' },
      { key: 'auth_token', label: '注册 Token', type: 'password', placeholder: '留空表示不修改已保存 Token' },
      { key: 'dashboard_host', label: 'Dashboard 地址' },
      { key: 'dashboard_port', label: 'Dashboard 端口', type: 'number' },
      { key: 'dashboard_username', label: 'Dashboard 用户名' },
      { key: 'dashboard_password', label: 'Dashboard 密码', type: 'password', placeholder: '留空表示不修改已保存密码' },
      { key: 'allow_register', label: '允许 Agent 注册', type: 'checkbox' },
      { key: 'max_agents', label: '最大接入数量', type: 'number' },
      { key: 'status', label: '状态', type: 'select', options: [['configured', '已配置'], ['available', '可用'], ['unconfigured', '未配置'], ['unavailable', '不可用'], ['disabled', '已禁用']] },
      { key: 'remark', label: '备注', type: 'textarea' },
    ],
    actions: [
      { label: '测试', permission: 'test', endpoint: (item) => `/security/frp/servers/${item.id}/test/`, method: 'POST' },
      { label: '同步客户端', permission: 'sync_runtime', endpoint: (item) => `/security/frp/servers/${item.id}/sync-runtime/`, method: 'POST' },
      { label: '禁用/启用', permission: 'disable', labelFor: (item) => item.status === 'disabled' ? '启用' : '禁用', endpoint: (item) => item.status === 'disabled' ? `/security/frp/servers/${item.id}/enable/` : `/security/frp/servers/${item.id}/disable/`, method: 'POST' },
    ],
  },
  '/security/frp/agents': {
    title: 'frpc客户端',
    description: '',
    endpoint: '/security/frp/agents/',
    compactTable: true,
    compactTableFill: true,
    searchPlaceholder: '搜索主机名、Agent ID 或服务端',
    columns: [
      ['hostname', '主机名'],
      ['server_name', '服务端'],
      ['admin_host', '管理地址'],
      ['admin_port', '管理端口'],
      ['store_enabled', 'Store'],
      ['runtime_proxy_count', '端口数'],
      ['source', '来源'],
      ['approval_status', '审核'],
      ['status', '在线'],
      ['last_seen_at', '最近同步'],
    ],
    fields: [
      { key: 'server', label: '所属服务端', type: 'select', optionEndpoint: '/security/frp/servers/', optionLabel: 'name', optionValue: 'id', required: true },
      { key: 'hostname', label: '主机名', required: true },
      { key: 'source', label: '来源', type: 'select', options: [['manual', '手动维护'], ['frps_dashboard', 'frps Dashboard'], ['agent_report', 'Agent 上报']] },
      { key: 'admin_host', label: 'frpc 管理地址', placeholder: '例如 47.120.40.124' },
      { key: 'admin_port', label: 'frpc 管理端口', type: 'number' },
      { key: 'admin_username', label: 'frpc 管理用户名', placeholder: '默认继承服务端配置' },
      { key: 'admin_password', label: 'frpc 管理密码', type: 'password', placeholder: '留空表示继承服务端或不修改' },
      { key: 'tags', label: '标签', type: 'list', placeholder: 'prod, ssh, frp' },
      { key: 'approval_status', label: '审核状态', type: 'select', options: [['pending', '待审核'], ['approved', '已通过'], ['rejected', '已拒绝']] },
      { key: 'status', label: '在线状态', type: 'select', options: [['online', '在线'], ['offline', '离线'], ['unavailable', '异常'], ['disabled', '已禁用']] },
      { key: 'remark', label: '备注', type: 'textarea' },
    ],
    actions: [
      { label: '查看端口', permission: 'view_proxies', navigateTo: (item) => `/security/frp/proxies?agent=${item.id}` },
      { label: '测试', permission: 'test', endpoint: (item) => `/security/frp/agents/${item.id}/test/`, method: 'POST' },
      { label: '同步端口', permission: 'sync_proxies', endpoint: (item) => `/security/frp/agents/${item.id}/sync-proxies/`, method: 'POST' },
      {
        label: '新增端口',
        permission: 'add_proxy',
        endpoint: (item) => `/security/frp/agents/${item.id}/add-proxy/`,
        method: 'POST',
        fields: [
          { key: 'name', label: '端口名称', required: true, placeholder: '例如 ssh-tcp' },
          { key: 'proxy_type', label: '协议类型', type: 'select', options: [['tcp', 'TCP'], ['udp', 'UDP']], default: 'tcp' },
          { key: 'local_ip', label: '本地地址', required: true, default: '127.0.0.1' },
          { key: 'local_port', label: '本地端口', type: 'number', required: true, default: 22 },
          { key: 'remote_port', label: '远端端口', type: 'number', required: true, placeholder: '必须在服务端允许端口范围内' },
          { key: 'use_encryption', label: '启用加密', type: 'checkbox', default: true },
          { key: 'use_compression', label: '启用压缩', type: 'checkbox', default: true },
          { key: 'remark', label: '备注', type: 'textarea' },
        ],
      },
    ],
  },
  '/security/frp/proxies': {
    title: 'FRP 隧道配置',
    description: '',
    endpoint: '/security/frp/proxies/',
    compactTable: true,
    compactTableFill: true,
    searchPlaceholder: '搜索隧道名称、Agent、服务端或本地地址',
    columns: [
      ['name', '隧道名称'],
      ['agent_name', 'Agent'],
      ['proxy_type', '类型'],
      ['local_ip', '本地地址'],
      ['local_port', '本地端口'],
      ['remote_port', '远端端口'],
      ['today_traffic', '今日流量'],
      ['traffic', '合计流量'],
      ['status', '状态'],
      ['last_test_at', '最近测试'],
    ],
    fields: [
      { key: 'agent', label: 'Agent', type: 'select', optionEndpoint: '/security/frp/agents/?approval_status=approved', optionLabel: 'hostname', optionValue: 'id', required: true },
      { key: 'name', label: '隧道名称', required: true },
      { key: 'proxy_type', label: '代理类型', type: 'select', options: [['tcp', 'TCP'], ['udp', 'UDP']], default: 'tcp' },
      { key: 'local_ip', label: '本地地址', required: true, default: '127.0.0.1' },
      { key: 'local_port', label: '本地端口', type: 'number', required: true, default: 22 },
      { key: 'remote_port', label: '远端端口', type: 'number', required: true },
      { key: 'custom_domains', label: '自定义域名', type: 'list', placeholder: 'a.example.com, b.example.com' },
      { key: 'subdomain', label: '子域名' },
      { key: 'status', label: '状态', type: 'select', options: [['configured', '已配置'], ['available', '可用'], ['unavailable', '不可用'], ['disabled', '已禁用']] },
      { key: 'remark', label: '备注', type: 'textarea' },
    ],
    actions: [
      { label: '测试', permission: 'test', endpoint: (item) => `/security/frp/proxies/${item.id}/test/`, method: 'POST' },
      { label: '禁用/启用', permission: 'disable', labelFor: (item) => item.status === 'disabled' ? '启用' : '禁用', endpoint: (item) => item.status === 'disabled' ? `/security/frp/proxies/${item.id}/enable/` : `/security/frp/proxies/${item.id}/disable/`, method: 'POST' },
    ],
  },
  '/security/frp/audits': {
    title: 'FRP 连接审计',
    description: '',
    endpoint: '/security/frp/audits/',
    readonly: true,
    compactTable: true,
    compactTableFill: true,
    searchPlaceholder: '搜索操作者、动作、资源或来源 IP',
    columns: [
      ['created_at', '时间'],
      ['actor', '操作者'],
      ['action', '动作'],
      ['resource', '资源'],
      ['ip_address', '来源 IP'],
    ],
    fields: [
      { key: 'created_at', label: '时间', readonly: true },
      { key: 'actor', label: '操作者', readonly: true },
      { key: 'action', label: '动作', readonly: true },
      { key: 'resource', label: '资源', readonly: true },
      { key: 'ip_address', label: '来源 IP', readonly: true },
      { key: 'detail', label: '详情', type: 'json', readonly: true },
    ],
  },
}
