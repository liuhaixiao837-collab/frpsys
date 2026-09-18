<script setup lang="ts">
import { Check, LoaderCircle, MoveRight, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '../api'

type Challenge = {
  challenge_token: string
  scene_seed: number
  target_x: number
  target_y: number
  canvas_width: number
  canvas_height: number
  piece_size: number
}

type SliderStage = 'loading' | 'ready' | 'verifying' | 'success' | 'error'

const emit = defineEmits<{ verified: [token: string] }>()
const sceneCanvas = ref<HTMLCanvasElement | null>(null)
const pieceCanvas = ref<HTMLCanvasElement | null>(null)
const trackElement = ref<HTMLElement | null>(null)
const challenge = ref<Challenge | null>(null)
const stage = ref<SliderStage>('loading')
const offsetX = ref(0)
const error = ref('')
const dragging = ref(false)
const sceneVisible = ref(false)
const dragPointerId = ref<number | null>(null)
const dragOriginClientX = ref(0)
const dragOriginOffset = ref(0)
const dragStartedAt = ref(0)

const maxOffset = computed(() => challenge.value
  ? challenge.value.canvas_width - challenge.value.piece_size
  : 1)
const progress = computed(() => Math.max(0, Math.min(1, offsetX.value / maxOffset.value)))
const sceneStyle = computed(() => ({
  aspectRatio: challenge.value
    ? `${challenge.value.canvas_width} / ${challenge.value.canvas_height}`
    : '320 / 140',
}))
const pieceStyle = computed(() => {
  if (!challenge.value) return {}
  return {
    left: `${(offsetX.value / challenge.value.canvas_width) * 100}%`,
    top: `${(challenge.value.target_y / challenge.value.canvas_height) * 100}%`,
    width: `${(challenge.value.piece_size / challenge.value.canvas_width) * 100}%`,
    height: `${(challenge.value.piece_size / challenge.value.canvas_height) * 100}%`,
  }
})
const handleStyle = computed(() => ({
  left: `calc(${progress.value * 100}% - ${progress.value * 48}px)`,
}))
const fillStyle = computed(() => ({
  width: `calc(${progress.value * 100}% - ${progress.value * 48}px + 24px)`,
}))
const instruction = computed(() => ({
  loading: '正在生成拼图',
  ready: '向右拖动滑块完成拼图',
  verifying: '正在验证',
  success: '验证成功',
  error: error.value || '验证失败，请刷新重试',
}[stage.value]))

/**
 * 将数值限制在指定最小值和最大值之间。
 * 参数：`value` 为原始数值；`minimum`、`maximum` 为允许边界。
 * 返回：限制后的数值。
 * 副作用：不修改组件状态。
 */
function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value))
}

/**
 * 创建可复现的伪随机数生成器，使背景和拼图块绘制完全一致。
 * 参数：`seed` 为服务端下发的随机场景种子。
 * 返回：每次调用返回零到一之间数值的函数。
 * 副作用：只推进当前局部随机状态。
 */
function seededRandom(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 4294967296
  }
}

/**
 * 绘制拼图块轮廓，背景缺口与移动块共用同一形状。
 * 参数：`context` 为画布上下文；`x`、`y` 为起点；`size` 为拼图尺寸。
 * 返回：无显式返回值。
 * 副作用：修改当前画布路径，不直接填充或描边。
 */
function puzzlePath(context: CanvasRenderingContext2D, x: number, y: number, size: number) {
  const unit = size / 4
  context.beginPath()
  context.moveTo(x, y + unit)
  context.lineTo(x + unit, y + unit)
  context.bezierCurveTo(x + unit * .82, y, x + unit * 2.18, y, x + unit * 2, y + unit)
  context.lineTo(x + size, y + unit)
  context.lineTo(x + size, y + unit * 2)
  context.bezierCurveTo(x + size - unit, y + unit * 1.82, x + size - unit, y + unit * 3.18, x + size, y + unit * 3)
  context.lineTo(x + size, y + size)
  context.lineTo(x + unit * 2, y + size)
  context.bezierCurveTo(x + unit * 2.18, y + size - unit, x + unit * .82, y + size - unit, x + unit, y + size)
  context.lineTo(x, y + size)
  context.closePath()
}

/** 绘制随机山谷与河流场景。 */
function drawValley(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#8ed0e7')
  sky.addColorStop(1, '#f3d7a1')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  const mountainColors = ['#718b91', '#4f7375', '#315b58']
  mountainColors.forEach((color, layer) => {
    const baseY = height * (.5 + layer * .09)
    context.fillStyle = color
    context.beginPath()
    context.moveTo(0, baseY)
    for (let x = 0; x <= width; x += 32) {
      context.lineTo(x + 16, baseY - (16 + random() * 30) * (1 - layer * .12))
      context.lineTo(x + 32, baseY + random() * 7)
    }
    context.lineTo(width, height)
    context.lineTo(0, height)
    context.closePath()
    context.fill()
  })
  context.fillStyle = '#32766c'
  context.fillRect(0, height * .72, width, height * .28)
  context.fillStyle = '#71c0cb'
  context.beginPath()
  context.moveTo(width * .3, height)
  context.bezierCurveTo(width * .4, height * .76, width * .58, height * .86, width * .7, height * .67)
  context.lineTo(width * .83, height * .67)
  context.bezierCurveTo(width * .65, height * .88, width * .61, height * .94, width * .57, height)
  context.closePath()
  context.fill()
}

/** 绘制夜间城市与灯光场景。 */
function drawCity(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#14244a')
  sky.addColorStop(.66, '#70506f')
  sky.addColorStop(1, '#e49b6d')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = '#eef4ff'
  context.beginPath()
  context.arc(width * .78, height * .2, 10, 0, Math.PI * 2)
  context.fill()
  for (let index = 0; index < 34; index += 1) {
    context.fillStyle = index % 3 ? 'rgba(255,255,255,.72)' : 'rgba(252,211,77,.86)'
    context.fillRect(random() * width, random() * height * .48, 1.4, 1.4)
  }
  let x = 0
  while (x < width) {
    const buildingWidth = 18 + Math.floor(random() * 24)
    const buildingHeight = 34 + Math.floor(random() * 46)
    const top = height - buildingHeight
    context.fillStyle = random() > .5 ? '#17223b' : '#24304a'
    context.fillRect(x, top, buildingWidth, buildingHeight)
    for (let windowY = top + 9; windowY < height - 7; windowY += 11) {
      for (let windowX = x + 6; windowX < x + buildingWidth - 4; windowX += 9) {
        context.fillStyle = random() > .42 ? '#f6c967' : '#43516c'
        context.fillRect(windowX, windowY, 3, 4)
      }
    }
    x += buildingWidth + 3
  }
}

/** 绘制森林、溪流与树木场景。 */
function drawForest(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#b9e1d0')
  sky.addColorStop(.56, '#e9e0ae')
  sky.addColorStop(1, '#55785d')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = '#4e8065'
  context.beginPath()
  context.moveTo(0, height * .7)
  context.quadraticCurveTo(width * .25, height * .48, width * .5, height * .68)
  context.quadraticCurveTo(width * .75, height * .45, width, height * .64)
  context.lineTo(width, height)
  context.lineTo(0, height)
  context.fill()
  for (let index = 0; index < 24; index += 1) {
    const treeX = random() * width
    const treeY = height * (.48 + random() * .36)
    const treeSize = 12 + random() * 24
    context.fillStyle = '#4b3a2e'
    context.fillRect(treeX - 2, treeY, 4, treeSize * .55)
    context.fillStyle = index % 3 === 0 ? '#1f5948' : '#2f7154'
    context.beginPath()
    context.moveTo(treeX, treeY - treeSize)
    context.lineTo(treeX - treeSize * .42, treeY + treeSize * .28)
    context.lineTo(treeX + treeSize * .42, treeY + treeSize * .28)
    context.closePath()
    context.fill()
  }
  context.strokeStyle = '#9ad9d2'
  context.lineWidth = 11
  context.beginPath()
  context.moveTo(width * .62, height)
  context.bezierCurveTo(width * .45, height * .82, width * .7, height * .72, width * .54, height * .57)
  context.stroke()
}

/** 绘制海岸、灯塔与帆船场景。 */
function drawCoast(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#80c7dc')
  sky.addColorStop(.54, '#d6edf0')
  sky.addColorStop(.55, '#3f92a9')
  sky.addColorStop(1, '#17677c')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = '#56666a'
  context.beginPath()
  context.moveTo(0, height)
  context.lineTo(0, height * .63)
  context.quadraticCurveTo(width * .2, height * .52, width * .38, height)
  context.fill()
  context.fillStyle = '#f3eee2'
  context.fillRect(width * .17, height * .27, 18, 59)
  context.fillStyle = '#d45145'
  context.beginPath()
  context.moveTo(width * .15, height * .28)
  context.lineTo(width * .2, height * .28)
  context.lineTo(width * .175, height * .13)
  context.closePath()
  context.fill()
  context.fillStyle = '#243b4b'
  context.fillRect(width * .185, height * .4, 4, 8)
  for (let index = 0; index < 10; index += 1) {
    const waveX = width * (.38 + random() * .58)
    const waveY = height * (.62 + random() * .3)
    context.strokeStyle = 'rgba(226,247,250,.72)'
    context.lineWidth = 1.5
    context.beginPath()
    context.arc(waveX, waveY, 8 + random() * 13, Math.PI * .1, Math.PI * .9)
    context.stroke()
  }
  context.fillStyle = '#f7f1d2'
  context.beginPath()
  context.moveTo(width * .73, height * .55)
  context.lineTo(width * .73, height * .82)
  context.lineTo(width * .61, height * .72)
  context.closePath()
  context.fill()
}

/** 绘制星空、行星与地表场景。 */
function drawSpace(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, width, height)
  sky.addColorStop(0, '#10152f')
  sky.addColorStop(.58, '#263a68')
  sky.addColorStop(1, '#512f62')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  for (let index = 0; index < 62; index += 1) {
    const size = .7 + random() * 1.8
    context.fillStyle = index % 5 === 0 ? '#f8d98a' : '#eef5ff'
    context.beginPath()
    context.arc(random() * width, random() * height * .82, size, 0, Math.PI * 2)
    context.fill()
  }
  const planet = context.createRadialGradient(width * .74, height * .28, 2, width * .74, height * .28, 25)
  planet.addColorStop(0, '#ffe5a8')
  planet.addColorStop(.58, '#df8a72')
  planet.addColorStop(1, '#704966')
  context.fillStyle = planet
  context.beginPath()
  context.arc(width * .74, height * .28, 25, 0, Math.PI * 2)
  context.fill()
  context.strokeStyle = 'rgba(246,220,170,.72)'
  context.lineWidth = 4
  context.beginPath()
  context.ellipse(width * .74, height * .28, 37, 10, -.18, 0, Math.PI * 2)
  context.stroke()
  context.fillStyle = '#17243e'
  context.beginPath()
  context.moveTo(0, height)
  for (let x = 0; x <= width; x += 24) context.lineTo(x, height * (.78 + random() * .17))
  context.lineTo(width, height)
  context.closePath()
  context.fill()
}

/**
 * 绘制雪山、冰湖与松林场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入雪山主题像素。
 */
function drawSnowMountain(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const dawn = random() > .5
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, dawn ? '#7fa6cf' : '#92c9e8')
  sky.addColorStop(1, dawn ? '#f3c6a5' : '#e8f5f8')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  for (let layer = 0; layer < 3; layer += 1) {
    const baseY = height * (.56 + layer * .1)
    const peakX = width * (.2 + random() * .58)
    const peakY = height * (.16 + layer * .1 + random() * .08)
    context.fillStyle = ['#dce8ef', '#9fb7c7', '#667f91'][layer]
    context.beginPath()
    context.moveTo(-20, baseY)
    context.lineTo(peakX, peakY)
    context.lineTo(width + 20, baseY + random() * 10)
    context.lineTo(width, height)
    context.lineTo(0, height)
    context.closePath()
    context.fill()
    context.fillStyle = 'rgba(255,255,255,.86)'
    context.beginPath()
    context.moveTo(peakX, peakY)
    context.lineTo(peakX - 24 - random() * 20, peakY + 35)
    context.lineTo(peakX - 5, peakY + 27)
    context.lineTo(peakX + 9, peakY + 40)
    context.lineTo(peakX + 38, peakY + 48)
    context.closePath()
    context.fill()
  }
  context.fillStyle = '#75a9ba'
  context.fillRect(0, height * .78, width, height * .22)
  for (let index = 0; index < 13; index += 1) {
    const treeX = random() * width
    const treeY = height * (.7 + random() * .24)
    const treeSize = 8 + random() * 15
    context.fillStyle = '#244f50'
    context.beginPath()
    context.moveTo(treeX, treeY - treeSize)
    context.lineTo(treeX - treeSize * .42, treeY)
    context.lineTo(treeX + treeSize * .42, treeY)
    context.closePath()
    context.fill()
  }
}

/**
 * 绘制沙漠、沙丘与绿洲场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入沙漠主题像素。
 */
function drawDesert(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sunset = random() > .45
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, sunset ? '#6879a6' : '#62b8d0')
  sky.addColorStop(1, sunset ? '#f5a462' : '#f4d59a')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = sunset ? '#ffe0a3' : '#fff1b8'
  context.beginPath()
  context.arc(width * (.2 + random() * .62), height * .22, 12 + random() * 7, 0, Math.PI * 2)
  context.fill()
  const duneColors = ['#e9b56f', '#cf8a4e', '#a8613f']
  duneColors.forEach((color, layer) => {
    const baseY = height * (.58 + layer * .12)
    context.fillStyle = color
    context.beginPath()
    context.moveTo(0, height)
    context.lineTo(0, baseY)
    context.bezierCurveTo(width * .24, baseY - 35 - random() * 18, width * .38, baseY + 15, width * .58, baseY - 12)
    context.bezierCurveTo(width * .75, baseY - 34, width * .88, baseY + 3, width, baseY - 15)
    context.lineTo(width, height)
    context.closePath()
    context.fill()
  })
  context.fillStyle = '#307b68'
  context.beginPath()
  context.ellipse(width * .72, height * .8, 27, 8, 0, 0, Math.PI * 2)
  context.fill()
  for (let index = 0; index < 5; index += 1) {
    const palmX = width * (.65 + random() * .16)
    const palmY = height * (.69 + random() * .1)
    context.strokeStyle = '#6b4934'
    context.lineWidth = 3
    context.beginPath()
    context.moveTo(palmX, palmY + 20)
    context.quadraticCurveTo(palmX + 4, palmY + 8, palmX, palmY - 12)
    context.stroke()
    context.strokeStyle = '#285e47'
    context.lineWidth = 4
    for (let leaf = 0; leaf < 5; leaf += 1) {
      context.beginPath()
      context.moveTo(palmX, palmY - 11)
      context.lineTo(palmX + Math.cos(leaf * 1.25) * 13, palmY - 11 + Math.sin(leaf * 1.25) * 7)
      context.stroke()
    }
  }
}

/**
 * 绘制静谧湖泊、倒影与飞鸟场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入湖泊主题像素。
 */
function drawLake(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const misty = random() > .5
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, misty ? '#8ea9b7' : '#6eb6d1')
  sky.addColorStop(.56, misty ? '#d9ddd2' : '#d6e7c4')
  sky.addColorStop(.57, misty ? '#789ba1' : '#4f9ca1')
  sky.addColorStop(1, '#284f61')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = misty ? '#607c79' : '#4e7162'
  context.beginPath()
  context.moveTo(0, height * .57)
  for (let x = 0; x <= width; x += 35) context.lineTo(x, height * (.4 + random() * .13))
  context.lineTo(width, height * .61)
  context.lineTo(0, height * .61)
  context.closePath()
  context.fill()
  for (let index = 0; index < 16; index += 1) {
    const rippleX = random() * width
    const rippleY = height * (.61 + random() * .32)
    context.strokeStyle = `rgba(218,242,238,${.18 + random() * .35})`
    context.lineWidth = 1
    context.beginPath()
    context.ellipse(rippleX, rippleY, 5 + random() * 18, 2 + random() * 3, 0, 0, Math.PI * 2)
    context.stroke()
  }
  context.strokeStyle = '#263e49'
  context.lineWidth = 1.4
  for (let index = 0; index < 5; index += 1) {
    const birdX = width * (.16 + random() * .67)
    const birdY = height * (.15 + random() * .23)
    context.beginPath()
    context.arc(birdX - 4, birdY, 4, Math.PI * 1.1, Math.PI * 1.9)
    context.arc(birdX + 4, birdY, 4, Math.PI * 1.1, Math.PI * 1.9)
    context.stroke()
  }
}

/**
 * 绘制竹林、雾气与石径场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入竹林主题像素。
 */
function drawBamboo(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const warm = random() > .52
  const background = context.createLinearGradient(0, 0, width, height)
  background.addColorStop(0, warm ? '#c7d3a1' : '#9cc4ac')
  background.addColorStop(1, warm ? '#4a6c4b' : '#355f57')
  context.fillStyle = background
  context.fillRect(0, 0, width, height)
  for (let index = 0; index < 26; index += 1) {
    const bambooX = random() * width
    const thickness = 3 + random() * 5
    const lean = (random() - .5) * 16
    context.strokeStyle = index % 4 === 0 ? '#183f35' : '#2d6046'
    context.lineWidth = thickness
    context.beginPath()
    context.moveTo(bambooX, height)
    context.lineTo(bambooX + lean, -8)
    context.stroke()
    context.strokeStyle = 'rgba(212,231,173,.48)'
    context.lineWidth = 1
    for (let joint = 18; joint < height; joint += 22 + random() * 8) {
      context.beginPath()
      context.moveTo(bambooX + lean * (1 - joint / height) - thickness, joint)
      context.lineTo(bambooX + lean * (1 - joint / height) + thickness, joint)
      context.stroke()
    }
  }
  context.fillStyle = 'rgba(223,231,205,.24)'
  context.fillRect(0, height * .28, width, height * .2)
  context.fillStyle = '#a7aa8a'
  context.beginPath()
  context.moveTo(width * .39, height)
  context.bezierCurveTo(width * .47, height * .78, width * .43, height * .62, width * .55, height * .48)
  context.lineTo(width * .64, height * .48)
  context.bezierCurveTo(width * .51, height * .68, width * .59, height * .84, width * .61, height)
  context.closePath()
  context.fill()
}

/**
 * 绘制梯田、水面与农舍场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入梯田主题像素。
 */
function drawTerraces(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const season = Math.floor(random() * 3)
  const skyColors = [['#74bad0', '#e9d9a4'], ['#94b5ce', '#efc79f'], ['#a7c7bc', '#e8e2bd']][season]
  const fieldColors = [
    ['#6fa55b', '#416f47'],
    ['#d5a744', '#8d6a35'],
    ['#6e9f75', '#416c5c'],
  ][season]
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, skyColors[0])
  sky.addColorStop(1, skyColors[1])
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = '#58745f'
  context.beginPath()
  context.moveTo(0, height * .5)
  context.quadraticCurveTo(width * .34, height * .28, width * .62, height * .48)
  context.quadraticCurveTo(width * .82, height * .34, width, height * .51)
  context.lineTo(width, height)
  context.lineTo(0, height)
  context.closePath()
  context.fill()
  for (let layer = 0; layer < 7; layer += 1) {
    const y = height * (.48 + layer * .075)
    context.strokeStyle = fieldColors[layer % 2]
    context.lineWidth = 8 + layer * 1.7
    context.beginPath()
    context.moveTo(-10, y)
    context.bezierCurveTo(width * .2, y - 13 - random() * 7, width * .48, y + 12, width * .7, y - 5)
    context.bezierCurveTo(width * .84, y - 12, width * .94, y + 4, width + 12, y - 8)
    context.stroke()
    context.strokeStyle = 'rgba(220,239,217,.48)'
    context.lineWidth = 1
    context.stroke()
  }
  context.fillStyle = '#e8dbc1'
  context.fillRect(width * .68, height * .34, 22, 14)
  context.fillStyle = '#74483d'
  context.beginPath()
  context.moveTo(width * .66, height * .35)
  context.lineTo(width * .72, height * .24)
  context.lineTo(width * .77, height * .35)
  context.closePath()
  context.fill()
}

/**
 * 绘制港口、货轮与起重机场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入港口主题像素。
 */
function drawHarbor(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const night = random() > .55
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, night ? '#26375d' : '#70acc1')
  sky.addColorStop(.58, night ? '#8b6271' : '#d3d6c5')
  sky.addColorStop(.59, night ? '#233c58' : '#417e91')
  sky.addColorStop(1, '#173c50')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  for (let index = 0; index < 4; index += 1) {
    const craneX = 24 + index * 66 + random() * 18
    const craneTop = height * (.23 + random() * .12)
    context.strokeStyle = night ? '#182237' : '#394d55'
    context.lineWidth = 4
    context.beginPath()
    context.moveTo(craneX, height * .65)
    context.lineTo(craneX, craneTop)
    context.lineTo(craneX + 43, craneTop)
    context.lineTo(craneX + 12, craneTop + 16)
    context.stroke()
  }
  context.fillStyle = '#263746'
  context.beginPath()
  context.moveTo(width * .28, height * .72)
  context.lineTo(width * .8, height * .72)
  context.lineTo(width * .7, height * .84)
  context.lineTo(width * .37, height * .84)
  context.closePath()
  context.fill()
  const containers = ['#c25445', '#d2953f', '#33727a', '#526e9b']
  for (let index = 0; index < 9; index += 1) {
    context.fillStyle = containers[Math.floor(random() * containers.length)]
    context.fillRect(width * .4 + (index % 5) * 21, height * .48 + Math.floor(index / 5) * 15, 19, 13)
  }
  for (let index = 0; index < 9; index += 1) {
    context.strokeStyle = 'rgba(219,240,244,.38)'
    context.beginPath()
    context.moveTo(random() * width, height * (.86 + random() * .1))
    context.lineTo(random() * width, height * (.86 + random() * .1))
    context.stroke()
  }
}

/**
 * 绘制江南古镇、拱桥与灯笼场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入古镇主题像素。
 */
function drawAncientTown(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const evening = random() > .48
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, evening ? '#596c88' : '#a7c4c8')
  sky.addColorStop(1, evening ? '#d49b7b' : '#e5ddd0')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  context.fillStyle = '#b8afa1'
  context.fillRect(0, height * .54, width, height * .46)
  let houseX = 0
  while (houseX < width) {
    const houseWidth = 34 + random() * 25
    const top = height * (.34 + random() * .14)
    context.fillStyle = random() > .5 ? '#e5dfd0' : '#cfc8b9'
    context.fillRect(houseX, top, houseWidth, height * .58 - top)
    context.fillStyle = '#34424a'
    context.beginPath()
    context.moveTo(houseX - 5, top)
    context.lineTo(houseX + houseWidth * .5, top - 14)
    context.lineTo(houseX + houseWidth + 5, top)
    context.closePath()
    context.fill()
    if (evening) {
      context.fillStyle = '#e85f3f'
      context.beginPath()
      context.arc(houseX + houseWidth * .72, top + 15, 3.5, 0, Math.PI * 2)
      context.fill()
    }
    houseX += houseWidth + 4
  }
  context.fillStyle = '#315969'
  context.fillRect(0, height * .7, width, height * .3)
  context.strokeStyle = '#8d8172'
  context.lineWidth = 9
  context.beginPath()
  context.arc(width * .52, height * .72, 45, Math.PI, Math.PI * 2)
  context.stroke()
  context.strokeStyle = 'rgba(227,239,232,.42)'
  context.lineWidth = 1
  for (let index = 0; index < 10; index += 1) {
    const rippleY = height * (.77 + index * .021)
    context.beginPath()
    context.moveTo(width * .33 + random() * 24, rippleY)
    context.lineTo(width * .7 - random() * 22, rippleY)
    context.stroke()
  }
}

/**
 * 绘制峡谷、岩层与鹰群场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入峡谷主题像素。
 */
function drawCanyon(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, random() > .5 ? '#5fa9c4' : '#798cb0')
  sky.addColorStop(1, '#f1c082')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  const rockColors = ['#ad5d43', '#8c493a', '#643743']
  rockColors.forEach((color, layer) => {
    const inset = layer * 28
    context.fillStyle = color
    context.beginPath()
    context.moveTo(0, height)
    context.lineTo(0, height * (.22 + layer * .12))
    context.lineTo(width * (.25 + layer * .05), height * (.35 + random() * .08))
    context.lineTo(width * (.37 + layer * .03), height)
    context.lineTo(width * (.63 - layer * .03), height)
    context.lineTo(width * (.75 - layer * .05), height * (.32 + random() * .08))
    context.lineTo(width, height * (.2 + layer * .13))
    context.lineTo(width, height)
    context.closePath()
    context.fill()
    context.strokeStyle = 'rgba(244,172,111,.35)'
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(inset, height * (.48 + layer * .1))
    context.lineTo(width * (.27 + layer * .04), height * (.56 + layer * .08))
    context.stroke()
  })
  context.fillStyle = '#d69558'
  context.beginPath()
  context.moveTo(width * .42, height)
  context.lineTo(width * .49, height * .46)
  context.lineTo(width * .55, height * .46)
  context.lineTo(width * .64, height)
  context.closePath()
  context.fill()
  context.strokeStyle = '#3c3031'
  context.lineWidth = 1.2
  for (let index = 0; index < 4; index += 1) {
    const eagleX = width * (.35 + random() * .3)
    const eagleY = height * (.14 + random() * .18)
    context.beginPath()
    context.arc(eagleX - 4, eagleY, 4, Math.PI * 1.06, Math.PI * 1.9)
    context.arc(eagleX + 4, eagleY, 4, Math.PI * 1.1, Math.PI * 1.94)
    context.stroke()
  }
}

/**
 * 绘制草原、风车与云层场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入草原主题像素。
 */
function drawGrassland(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const spring = random() > .42
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#65b4d5')
  sky.addColorStop(.64, '#d8ecdd')
  sky.addColorStop(.65, spring ? '#6da650' : '#b18a45')
  sky.addColorStop(1, spring ? '#315f3f' : '#70502f')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  for (let index = 0; index < 5; index += 1) {
    const cloudX = random() * width
    const cloudY = height * (.12 + random() * .26)
    context.fillStyle = 'rgba(255,255,255,.7)'
    context.beginPath()
    context.arc(cloudX, cloudY, 8, 0, Math.PI * 2)
    context.arc(cloudX + 9, cloudY - 3, 11, 0, Math.PI * 2)
    context.arc(cloudX + 20, cloudY, 8, 0, Math.PI * 2)
    context.fill()
  }
  const windmillX = width * (.7 + random() * .12)
  const windmillY = height * .67
  context.fillStyle = '#e8dfce'
  context.fillRect(windmillX - 6, windmillY - 30, 12, 37)
  context.strokeStyle = '#624e41'
  context.lineWidth = 3
  for (let blade = 0; blade < 4; blade += 1) {
    const angle = blade * Math.PI / 2 + random() * .2
    context.beginPath()
    context.moveTo(windmillX, windmillY - 28)
    context.lineTo(windmillX + Math.cos(angle) * 23, windmillY - 28 + Math.sin(angle) * 23)
    context.stroke()
  }
  for (let index = 0; index < 45; index += 1) {
    context.fillStyle = index % 3 === 0 ? '#f5d15b' : '#e8eee0'
    context.fillRect(random() * width, height * (.69 + random() * .27), 1.5, 1.5)
  }
}

/**
 * 绘制极光、雪原与木屋场景。
 * 参数：`context` 为画布上下文；`random` 为种子随机函数；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：向当前 Canvas 写入极光主题像素。
 */
function drawAurora(context: CanvasRenderingContext2D, random: () => number, width: number, height: number) {
  const sky = context.createLinearGradient(0, 0, 0, height)
  sky.addColorStop(0, '#071a35')
  sky.addColorStop(.62, '#163b54')
  sky.addColorStop(1, '#385a68')
  context.fillStyle = sky
  context.fillRect(0, 0, width, height)
  for (let band = 0; band < 3; band += 1) {
    const aurora = context.createLinearGradient(0, 0, width, 0)
    aurora.addColorStop(0, 'rgba(52,211,153,0)')
    aurora.addColorStop(.35, band % 2 ? 'rgba(96,165,250,.48)' : 'rgba(52,211,153,.54)')
    aurora.addColorStop(.72, band % 2 ? 'rgba(167,139,250,.4)' : 'rgba(45,212,191,.42)')
    aurora.addColorStop(1, 'rgba(52,211,153,0)')
    context.strokeStyle = aurora
    context.lineWidth = 13 + random() * 10
    context.beginPath()
    context.moveTo(-10, height * (.18 + band * .1))
    context.bezierCurveTo(width * .24, height * (.05 + random() * .18), width * .55, height * (.38 + random() * .08), width + 10, height * (.12 + band * .08))
    context.stroke()
  }
  for (let index = 0; index < 42; index += 1) {
    context.fillStyle = 'rgba(241,248,255,.82)'
    context.fillRect(random() * width, random() * height * .58, 1, 1)
  }
  context.fillStyle = '#dce8eb'
  context.beginPath()
  context.moveTo(0, height)
  for (let x = 0; x <= width; x += 34) context.lineTo(x, height * (.7 + random() * .08))
  context.lineTo(width, height)
  context.closePath()
  context.fill()
  const cabinX = width * (.18 + random() * .45)
  context.fillStyle = '#563f38'
  context.fillRect(cabinX, height * .67, 38, 28)
  context.fillStyle = '#342b31'
  context.beginPath()
  context.moveTo(cabinX - 6, height * .68)
  context.lineTo(cabinX + 19, height * .53)
  context.lineTo(cabinX + 44, height * .68)
  context.closePath()
  context.fill()
  context.fillStyle = '#ffd978'
  context.fillRect(cabinX + 23, height * .73, 7, 8)
}

/**
 * 按种子从多套主题中绘制可复现的本地 Canvas 场景。
 * 参数：`context` 为画布上下文；`seed` 为场景种子；`width`、`height` 为画布尺寸。
 * 返回：无显式返回值。
 * 副作用：只向当前 Canvas 写入临时像素，不创建本地图片文件。
 */
function drawScene(context: CanvasRenderingContext2D, seed: number, width: number, height: number) {
  const random = seededRandom(seed)
  const scenes = [
    drawValley,
    drawCity,
    drawForest,
    drawCoast,
    drawSpace,
    drawSnowMountain,
    drawDesert,
    drawLake,
    drawBamboo,
    drawTerraces,
    drawHarbor,
    drawAncientTown,
    drawCanyon,
    drawGrassland,
    drawAurora,
  ]
  scenes[(seed >>> 0) % scenes.length](context, random, width, height)
}

/**
 * 清除浏览器内存中的临时 Canvas 像素。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清空背景和拼图块画布，不写入或删除任何本地文件。
 */
function clearGeneratedImage() {
  for (const canvas of [sceneCanvas.value, pieceCanvas.value]) {
    if (!canvas) continue
    canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height)
    canvas.width = 0
    canvas.height = 0
  }
}

/**
 * 把当前挑战绘制到背景画布和可移动拼图块画布。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：重绘两个 Canvas 元素。
 */
function drawChallenge() {
  const current = challenge.value
  const background = sceneCanvas.value
  const piece = pieceCanvas.value
  if (!current || !background || !piece) return
  background.width = current.canvas_width
  background.height = current.canvas_height
  piece.width = current.piece_size
  piece.height = current.piece_size
  const backgroundContext = background.getContext('2d')
  const pieceContext = piece.getContext('2d')
  if (!backgroundContext || !pieceContext) return

  drawScene(backgroundContext, current.scene_seed, current.canvas_width, current.canvas_height)
  puzzlePath(backgroundContext, current.target_x, current.target_y, current.piece_size)
  backgroundContext.fillStyle = 'rgba(241, 245, 249, .72)'
  backgroundContext.fill()
  backgroundContext.lineWidth = 2
  backgroundContext.strokeStyle = 'rgba(15, 23, 42, .58)'
  backgroundContext.stroke()

  pieceContext.save()
  puzzlePath(pieceContext, 0, 0, current.piece_size)
  pieceContext.clip()
  pieceContext.translate(-current.target_x, -current.target_y)
  drawScene(pieceContext, current.scene_seed, current.canvas_width, current.canvas_height)
  pieceContext.restore()
  puzzlePath(pieceContext, 0, 0, current.piece_size)
  pieceContext.lineWidth = 2
  pieceContext.strokeStyle = '#f8fafc'
  pieceContext.stroke()
}

/**
 * 请求新的拖拽挑战并恢复组件初始状态。
 * 参数：无。
 * 返回：挑战加载完成后的 Promise。
 * 副作用：请求后端、重绘画布并清空之前的验证凭证。
 */
async function loadChallenge() {
  clearGeneratedImage()
  stage.value = 'loading'
  challenge.value = null
  offsetX.value = 0
  error.value = ''
  dragging.value = false
  sceneVisible.value = false
  dragStartedAt.value = 0
  emit('verified', '')
  try {
    const result = await api('/auth/slider-captcha', { skipAuth: true })
    if (!result.enabled) {
      error.value = '图形拖拽验证已关闭'
      stage.value = 'error'
      return
    }
    challenge.value = result as Challenge
    stage.value = 'ready'
    await nextTick()
    drawChallenge()
  } catch (reason: any) {
    error.value = reason.message || '拼图加载失败'
    stage.value = 'error'
  }
}

/**
 * 开始跟踪鼠标或触摸拖拽。
 * 参数：`event` 为指针按下事件。
 * 返回：无显式返回值。
 * 副作用：捕获指针并记录拖拽起点。
 */
function startDrag(event: PointerEvent) {
  if (stage.value !== 'ready') return
  event.preventDefault()
  sceneVisible.value = true
  dragging.value = true
  dragPointerId.value = event.pointerId
  dragOriginClientX.value = event.clientX
  dragOriginOffset.value = offsetX.value
  dragStartedAt.value = performance.now()
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

/**
 * 根据指针移动距离同步滑块和拼图块位置。
 * 参数：`event` 为指针移动事件。
 * 返回：无显式返回值。
 * 副作用：更新当前挑战的横向拖拽位置。
 */
function moveDrag(event: PointerEvent) {
  if (!dragging.value || event.pointerId !== dragPointerId.value || !trackElement.value) return
  const travel = Math.max(1, trackElement.value.getBoundingClientRect().width - 48)
  const pixelDelta = event.clientX - dragOriginClientX.value
  offsetX.value = clamp(dragOriginOffset.value + pixelDelta / travel * maxOffset.value, 0, maxOffset.value)
}

/**
 * 结束拖拽并向服务端提交最终位置。
 * 参数：`event` 为指针释放事件。
 * 返回：无显式返回值。
 * 副作用：释放指针并触发一次后端验证请求。
 */
function finishDrag(event: PointerEvent) {
  if (!dragging.value || event.pointerId !== dragPointerId.value) return
  dragging.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  void verifyPosition()
}

/**
 * 取消被浏览器中断的拖拽并恢复滑块起始位置。
 * 参数：`event` 为指针取消事件。
 * 返回：无显式返回值。
 * 副作用：释放指针并重置当前拖拽状态。
 */
function cancelDrag(event: PointerEvent) {
  if (!dragging.value || event.pointerId !== dragPointerId.value) return
  dragging.value = false
  offsetX.value = dragOriginOffset.value
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

/**
 * 处理键盘方向键调整和回车验证，保证滑块可无鼠标操作。
 * 参数：`event` 为滑块按钮键盘事件。
 * 返回：无显式返回值。
 * 副作用：更新拖拽位置或触发后端验证。
 */
function handleKeydown(event: KeyboardEvent) {
  if (stage.value !== 'ready') return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault()
    sceneVisible.value = true
    if (!dragStartedAt.value) dragStartedAt.value = performance.now()
    offsetX.value = clamp(offsetX.value + (event.key === 'ArrowRight' ? 4 : -4), 0, maxOffset.value)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    void verifyPosition()
  }
}

/**
 * 提交横向位置和耗时，并保存后端签发的一次性登录凭证。
 * 参数：无。
 * 返回：验证请求完成后的 Promise。
 * 副作用：请求后端并更新验证状态，成功时通知登录表单。
 */
async function verifyPosition() {
  if (stage.value !== 'ready' || !challenge.value) return
  stage.value = 'verifying'
  try {
    const result = await api('/auth/slider-captcha', {
      method: 'POST',
      body: JSON.stringify({
        challenge_token: challenge.value.challenge_token,
        offset_x: Math.round(offsetX.value),
        elapsed_ms: Math.round(performance.now() - dragStartedAt.value),
      }),
      skipAuth: true,
    })
    stage.value = 'success'
    offsetX.value = challenge.value.target_x
    sceneVisible.value = false
    clearGeneratedImage()
    emit('verified', result.verification_token || '')
  } catch (reason: any) {
    error.value = reason.message || '拼图位置不正确，请重试'
    stage.value = 'error'
    emit('verified', '')
  }
}

/**
 * 销毁登录页临时挑战图形和前端参数。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清空 Canvas 内存并移除当前组件持有的挑战对象。
 */
function dispose() {
  sceneVisible.value = false
  clearGeneratedImage()
  challenge.value = null
  dragPointerId.value = null
  dragStartedAt.value = 0
}

onMounted(loadChallenge)
onBeforeUnmount(dispose)
defineExpose({ dispose, reset: loadChallenge })
</script>

<template>
  <section class="slider-captcha" :class="`is-${stage}`">
    <header>
      <span><ShieldCheck :size="16" />图形拖拽验证</span>
      <button type="button" title="刷新拼图" :disabled="stage === 'loading' || stage === 'verifying'" @click="loadChallenge">
        <RefreshCw :size="15" :class="{ spin: stage === 'loading' }" />
      </button>
    </header>
    <div ref="trackElement" class="slider-captcha-track">
      <span class="slider-captcha-fill" :style="fillStyle" />
      <span class="slider-captcha-instruction">{{ instruction }}</span>
      <button
        class="slider-captcha-handle"
        :class="{ dragging }"
        :style="handleStyle"
        type="button"
        role="slider"
        aria-label="拖动拼图滑块"
        aria-valuemin="0"
        :aria-valuemax="Math.round(maxOffset)"
        :aria-valuenow="Math.round(offsetX)"
        :disabled="stage !== 'ready'"
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="finishDrag"
        @pointercancel="cancelDrag"
        @keydown="handleKeydown"
      >
        <LoaderCircle v-if="stage === 'verifying'" :size="18" class="spin" />
        <Check v-else-if="stage === 'success'" :size="19" />
        <MoveRight v-else :size="19" />
      </button>
    </div>
    <div v-show="sceneVisible" class="slider-captcha-scene" :style="sceneStyle">
      <canvas ref="sceneCanvas" aria-hidden="true" />
      <canvas v-if="challenge" ref="pieceCanvas" class="slider-captcha-piece" :style="pieceStyle" aria-hidden="true" />
    </div>
  </section>
</template>
