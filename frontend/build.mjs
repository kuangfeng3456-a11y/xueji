import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { rollup } from 'rollup'
import { parse, compileScript, compileTemplate, compileStyle, rewriteDefault } from '@vue/compiler-sfc'

const root = path.dirname(fileURLToPath(import.meta.url))
// 收集各 SFC 的 <style>（含 scoped），构建结束后并入 dist/style.css
const sfcStyles = []

const aliases = {
  vue: path.join(root, 'node_modules/vue/dist/vue.esm-browser.prod.js'),
  'vue-router': path.join(root, 'node_modules/vue-router/dist/vue-router.esm-browser.prod.js')
}

function resolveFile(base) {
  const candidates = [base, `${base}.js`, `${base}.mjs`, `${base}.vue`, path.join(base, 'index.js')]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  }
  return null
}

function vuePlugin() {
  return {
    name: 'xueji-sfc',
    resolveId(source, importer) {
      if (aliases[source]) return aliases[source]
      if (source.startsWith('.') && importer) {
        const found = resolveFile(path.resolve(path.dirname(importer), source))
        if (found) return found
      }
      return null
    },
    transform(code, id) {
      if (id.endsWith('.css')) return { code: 'export default {}', map: null }
      if (!id.endsWith('.vue')) return null

      const { descriptor, errors } = parse(code, { filename: id })
      if (errors.length) throw errors[0]

      const hash = crypto.createHash('sha256').update(id).digest('hex').slice(0, 8)
      const scopeId = `data-v-${hash}`
      const script = compileScript(descriptor, { id: scopeId })
      const scriptCode = rewriteDefault(script.content, '__sfc_main__')

      const hasScoped = descriptor.styles.some((style) => style.scoped)
      for (const style of descriptor.styles) {
        const compiled = compileStyle({
          source: style.content,
          filename: id,
          id: scopeId,
          scoped: Boolean(style.scoped)
        })
        if (compiled.errors.length) throw compiled.errors[0]
        sfcStyles.push(compiled.code)
      }

      if (!descriptor.template) {
        return (
          `${scriptCode}\n` +
          `${hasScoped ? `__sfc_main__.__scopeId = ${JSON.stringify(scopeId)}\n` : ''}` +
          `export default __sfc_main__`
        )
      }

      const tpl = compileTemplate({
        source: descriptor.template.content,
        filename: id,
        id: scopeId,
        compilerOptions: { bindingMetadata: script.bindings }
      })
      if (tpl.errors.length) throw tpl.errors[0]

      const renderCode = tpl.code.replace('export function render', 'function render')
      return (
        `${scriptCode}\n${renderCode}\n` +
        `__sfc_main__.render = render\n` +
        `${hasScoped ? `__sfc_main__.__scopeId = ${JSON.stringify(scopeId)}\n` : ''}` +
        `__sfc_main__.__file = ${JSON.stringify(path.basename(id))}\n` +
        `export default __sfc_main__`
      )
    }
  }
}

async function build() {
  const outDir = path.join(root, 'dist')
  fs.rmSync(outDir, { recursive: true, force: true })
  fs.mkdirSync(path.join(outDir, 'assets'), { recursive: true })

  const bundle = await rollup({
    input: path.join(root, 'src/main.js'),
    plugins: [vuePlugin()]
  })

  await bundle.write({
    dir: outDir,
    format: 'iife',
    name: 'XuejiApp',
    entryFileNames: 'assets/app.js',
    inlineDynamicImports: true,
    sourcemap: false
  })
  await bundle.close()

  // 样式产物只合并启用中的样式表。
  // theme.css（纸感编辑风）已停用：它的选择器优先级更高，会把 style.css 的 SaaS 主题覆盖回米色。
  // 如需临时回滚，设置环境变量 XUEJI_THEME=paper 即可。
  const cssFiles = ['src/style.css']
    .concat(process.env.XUEJI_THEME === 'paper' ? ['src/theme.css'] : [])
    .map((file) => path.join(root, file))
  const css = cssFiles
    .filter((file) => fs.existsSync(file))
    .map((file) => fs.readFileSync(file, 'utf8'))
    .concat(sfcStyles)
    .join('\n\n')
  fs.writeFileSync(path.join(outDir, 'style.css'), css)

  const hashOf = (file) =>
    crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex').slice(0, 10)
  const cssHash = hashOf(path.join(outDir, 'style.css'))
  const jsHash = hashOf(path.join(outDir, 'assets/app.js'))
  const html = fs
    .readFileSync(path.join(root, 'index.html'), 'utf8')
    .replace('./style.css', `./style.css?v=${cssHash}`)
    .replace('./assets/app.js', `./assets/app.js?v=${jsHash}`)
  fs.writeFileSync(path.join(outDir, 'index.html'), html)

  const appSize = fs.statSync(path.join(outDir, 'assets/app.js')).size
  console.log(`构建完成：dist/index.html, dist/assets/app.js (${(appSize / 1024).toFixed(1)} KB)`)
}

build().catch((error) => {
  console.error('构建失败：', error)
  process.exit(1)
})