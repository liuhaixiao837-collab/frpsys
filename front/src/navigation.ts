import {
  Activity, Cable, ChartSpline, FileClock, FileText, Gauge, ListOrdered, MonitorCog, Network, Server,
  Settings, ShieldCheck, Users, Wrench,
} from 'lucide-vue-next'

const iconMap: Record<string, any> = {
  Activity,
  Cable,
  ChartSpline,
  FileClock,
  FileText,
  Gauge,
  ListOrdered,
  MonitorCog,
  Network,
  Server,
  Settings,
  ShieldCheck,
  Users,
  Wrench,
}

export type ManifestPage = {
  code: string
  name: string
  path?: string
  icon?: string
  sidebar?: boolean
  aliases?: Array<{ path: string; name: string }>
  children?: ManifestPage[]
}

export type ManifestGroup = {
  code: string
  name: string
  icon?: string
  path?: string
  pages: ManifestPage[]
}

export type NavigationItem = [string, string, any, string, string[], NavigationItem[]]
export type NavigationGroup = [string, NavigationItem[], string, any, string]

/**
 * 封装 icon 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`name` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function icon(name?: string) {
  return iconMap[name || ''] || Gauge
}

/**
 * 递归遍历数据库返回的页面节点并执行指定访问函数。
 * 参数：`pages` 表示该步骤所需的业务参数；`visit` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function walkPages(pages: ManifestPage[], visit: (page: ManifestPage) => void) {
  for (const page of pages) {
    visit(page)
    walkPages(page.children || [], visit)
  }
}

/**
 * 计算并返回 collectPagePaths 对应的业务数据。
 * 参数：`page` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function collectPagePaths(page: ManifestPage) {
  const paths: string[] = []
  walkPages([page], (item) => {
    if (item.path) paths.push(item.path)
  })
  return paths
}

export const pages: string[][] = []
export const navigationGroups: NavigationGroup[] = []

/**
 * 封装 configureNavigation 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`groups` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
export function configureNavigation(groups: ManifestGroup[]) {
  pages.splice(0)
  navigationGroups.splice(0)
  for (const group of groups) {
    walkPages(group.pages || [], (page) => {
      if (page.path && !page.code.startsWith('menu.')) pages.push([page.path, page.name])
      for (const alias of page.aliases || []) pages.push([alias.path, alias.name])
    })
    const items: NavigationItem[] = []
    for (const page of group.pages || []) {
      const paths = collectPagePaths(page)
      if (page.sidebar && (page.path || paths.length)) {
        items.push([page.path || paths[0] || '', page.name, icon(page.icon), page.code, paths, collectNavigationChildren(page.children || [])])
      }
    }
    navigationGroups.push([group.name, items, group.code, icon(group.icon), group.path || ''])
  }
}

/**
 * 计算并返回 collectNavigationChildren 对应的业务数据。
 * 参数：`pages` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function collectNavigationChildren(pages: ManifestPage[]): NavigationItem[] {
  const items: NavigationItem[] = []
  for (const page of pages) {
    const paths = collectPagePaths(page)
    if (page.sidebar && (page.path || paths.length)) {
      items.push([page.path || paths[0] || '', page.name, icon(page.icon), page.code, paths, collectNavigationChildren(page.children || [])])
    }
  }
  return items
}
