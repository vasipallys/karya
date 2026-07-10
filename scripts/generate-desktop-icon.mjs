import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const source = path.join(root, 'desktop', 'assets', 'icon.svg')
const output = path.join(root, 'desktop', 'assets', 'icon.png')

await mkdir(path.dirname(output), { recursive: true })
await sharp(source)
  .resize(1024, 1024)
  .png({ compressionLevel: 9 })
  .toFile(output)

console.log(`Desktop icon ready: ${output}`)
