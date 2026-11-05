import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import BrandMark from './components/BrandMark.vue'
import HeroDiagram from './components/HeroDiagram.vue'
import GanttView from './components/GanttView.vue'
import BarsCompare from './components/BarsCompare.vue'
import FlowRail from './components/FlowRail.vue'
import LayerStack from './components/LayerStack.vue'
import TierLadder from './components/TierLadder.vue'
import MatrixGrid from './components/MatrixGrid.vue'
import LineChart from './components/LineChart.vue'
import AlgoTree from './components/AlgoTree.vue'
import ChainRipple from './components/ChainRipple.vue'
import DispatchLab from './components/DispatchLab.vue'
import LagrangianPlayer from './components/LagrangianPlayer.vue'
import ExplosionChart from './components/ExplosionChart.vue'
import QuizSelf from './components/QuizSelf.vue'
import './style.css'

export default {
  extends: DefaultTheme,
  Layout() {
    return h(DefaultTheme.Layout, null, {
      'home-hero-image': () => h(HeroDiagram),
      'home-hero-info-before': () => h(BrandMark, { variant: 'pill' })
    })
  },
  enhanceApp({ app }) {
    app.component('BrandMark', BrandMark)
    app.component('GanttView', GanttView)
    app.component('BarsCompare', BarsCompare)
    app.component('FlowRail', FlowRail)
    app.component('LayerStack', LayerStack)
    app.component('TierLadder', TierLadder)
    app.component('MatrixGrid', MatrixGrid)
    app.component('LineChart', LineChart)
    app.component('AlgoTree', AlgoTree)
    app.component('ChainRipple', ChainRipple)
    app.component('DispatchLab', DispatchLab)
    app.component('LagrangianPlayer', LagrangianPlayer)
    app.component('ExplosionChart', ExplosionChart)
    app.component('QuizSelf', QuizSelf)
  }
}
