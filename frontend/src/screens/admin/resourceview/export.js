// Chart export: PNG / GIF / PDF, with no third-party dependencies.
//
// Everything starts from a live <svg> in the page. The SVG is cloned with its
// computed styles inlined (CSS classes and `var(--m3-*)` custom properties do
// not survive serialisation), rasterised onto a canvas, and then encoded:
//   PNG - canvas.toBlob
//   GIF - the GIF89a encoder below (canvas cannot encode GIF natively)
//   PDF - the minimal single-page writer below (image XObject + Helvetica title)

const STYLE_PROPS = [
  'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity',
  'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'opacity', 'visibility', 'display',
  'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor', 'dominant-baseline',
  'letter-spacing',
]

function inlineStyles(source, clone) {
  const computed = getComputedStyle(source)
  let decl = ''
  for (const prop of STYLE_PROPS) {
    const value = computed.getPropertyValue(prop)
    if (value) decl += `${prop}:${value};`
  }
  clone.setAttribute('style', decl)
  // Presentation attributes such as fill="var(--m3-surface)" cannot resolve once
  // the SVG is detached. The inlined style already carries the resolved value,
  // so drop the unresolvable attribute rather than leave it in the markup.
  for (const attribute of [...clone.attributes]) {
    if (attribute.value.includes('var(--')) clone.removeAttribute(attribute.name)
  }
  const sourceKids = source.children
  const cloneKids = clone.children
  for (let i = 0; i < sourceKids.length && i < cloneKids.length; i += 1) {
    inlineStyles(sourceKids[i], cloneKids[i])
  }
}

export function serializeSvg(svg) {
  const box = svg.viewBox?.baseVal
  const width = box?.width || svg.clientWidth || 800
  const height = box?.height || svg.clientHeight || 600
  const clone = svg.cloneNode(true)
  inlineStyles(svg, clone)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  return { markup: new XMLSerializer().serializeToString(clone), width, height }
}

/** Draw the SVG onto an opaque canvas (transparent PNGs export badly to PDF/GIF). */
export function rasterize(svg, scale = 2, background = '#ffffff') {
  const { markup, width, height } = serializeSvg(svg)
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(width * scale))
      canvas.height = Math.max(1, Math.round(height * scale))
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = background
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
      resolve(canvas)
    }
    image.onerror = () => reject(new Error('The chart could not be rendered for export.'))
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`
  })
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// --------------------------------------------------------------------------- //
// GIF89a
// --------------------------------------------------------------------------- //

/**
 * Reduce RGBA pixels to <=256 palette indices. Charts are mostly flat colour, so
 * the most-frequent colours are kept exactly and everything else (antialiased
 * edges) snaps to the nearest of them. The rgb->index cache keeps this linear
 * in pixels rather than pixels x palette.
 */
export function quantize(data, width, height) {
  const histogram = new Map()
  for (let i = 0; i < data.length; i += 4) {
    const key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
    histogram.set(key, (histogram.get(key) || 0) + 1)
  }
  let palette = histogram.size <= 256
    ? [...histogram.keys()]
    : [...histogram.entries()].sort((a, b) => b[1] - a[1]).slice(0, 256).map(([key]) => key)
  if (palette.length === 0) palette = [0xffffff]

  const reds = palette.map((c) => (c >> 16) & 255)
  const greens = palette.map((c) => (c >> 8) & 255)
  const blues = palette.map((c) => c & 255)

  const cache = new Map()
  const indices = new Uint8Array(width * height)
  for (let i = 0, p = 0; p < indices.length; i += 4, p += 1) {
    const key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
    let index = cache.get(key)
    if (index === undefined) {
      const r = data[i]
      const g = data[i + 1]
      const b = data[i + 2]
      let best = 0
      let bestDistance = Infinity
      for (let k = 0; k < palette.length; k += 1) {
        const dr = r - reds[k]
        const dg = g - greens[k]
        const db = b - blues[k]
        const distance = dr * dr + dg * dg + db * db
        if (distance < bestDistance) {
          bestDistance = distance
          best = k
          if (distance === 0) break
        }
      }
      index = best
      cache.set(key, index)
    }
    indices[p] = index
  }
  return { indices, palette }
}

/**
 * GIF-flavoured LZW: variable code width (minCodeSize+1 up to 12 bits), codes
 * packed LSB-first.
 *
 * Code-width timing is the easy thing to get wrong here. A decoder only adds a
 * dictionary entry once it reads the *following* code, so its next-free code
 * trails the encoder's by exactly one. The encoder must therefore widen when
 * `nextCode` passes `1 << codeSize` (not when it reaches it) or every decoder
 * reads the stream one bit-width out of step and the image is corrupt.
 */
export function lzwEncode(indices, minCodeSize) {
  const clearCode = 1 << minCodeSize
  const endCode = clearCode + 1
  const out = []
  let codeSize = minCodeSize + 1
  let nextCode = endCode + 1
  let dict = new Map()
  let acc = 0
  let accBits = 0

  const write = (code) => {
    acc |= code << accBits
    accBits += codeSize
    while (accBits >= 8) {
      out.push(acc & 0xff)
      acc >>>= 8
      accBits -= 8
    }
  }

  write(clearCode)
  if (indices.length === 0) {
    write(endCode)
    if (accBits > 0) out.push(acc & 0xff)
    return out
  }

  let prefix = indices[0]
  for (let i = 1; i < indices.length; i += 1) {
    const k = indices[i]
    const key = prefix * 256 + k
    const existing = dict.get(key)
    if (existing !== undefined) {
      prefix = existing
      continue
    }
    write(prefix)
    dict.set(key, nextCode)
    nextCode += 1
    if (nextCode === 4096) {
      write(clearCode)
      dict = new Map()
      nextCode = endCode + 1
      codeSize = minCodeSize + 1
    } else if (nextCode > (1 << codeSize) && codeSize < 12) {
      codeSize += 1
    }
    prefix = k
  }
  write(prefix)
  write(endCode)
  if (accBits > 0) out.push(acc & 0xff)
  return out
}

export function encodeGif(data, width, height) {
  const { indices, palette } = quantize(data, width, height)
  let bits = 1
  while ((1 << bits) < palette.length) bits += 1
  bits = Math.min(8, Math.max(2, bits))
  const tableSize = 1 << bits

  const bytes = []
  const putString = (text) => { for (let i = 0; i < text.length; i += 1) bytes.push(text.charCodeAt(i) & 255) }
  const put16 = (value) => { bytes.push(value & 255, (value >> 8) & 255) }

  putString('GIF89a')
  put16(width)
  put16(height)
  bytes.push(0x80 | ((bits - 1) << 4) | (bits - 1)) // global colour table, depth, size
  bytes.push(0) // background colour index
  bytes.push(0) // default pixel aspect ratio
  for (let i = 0; i < tableSize; i += 1) {
    const colour = palette[i] ?? 0
    bytes.push((colour >> 16) & 255, (colour >> 8) & 255, colour & 255)
  }

  bytes.push(0x2c) // image descriptor
  put16(0); put16(0); put16(width); put16(height)
  bytes.push(0) // no local colour table, not interlaced

  bytes.push(bits)
  const lzw = lzwEncode(indices, bits)
  for (let i = 0; i < lzw.length; i += 255) {
    const chunk = lzw.slice(i, i + 255)
    bytes.push(chunk.length)
    for (const byte of chunk) bytes.push(byte)
  }
  bytes.push(0) // block terminator
  bytes.push(0x3b) // trailer
  return new Uint8Array(bytes)
}

// --------------------------------------------------------------------------- //
// PDF (single page, one image XObject, Helvetica caption)
// --------------------------------------------------------------------------- //

const A4_SHORT = 595.28
const A4_LONG = 841.89

// Caption text is written with the standard Helvetica font, whose encoding is
// WinAnsi. Byte-truncating a code point above 255 would silently emit a control
// character (an em dash became 0x14), so map the typography we actually produce
// and replace anything else unrepresentable.
const WIN_ANSI = new Map([
  [0x2013, 0x96], [0x2014, 0x97], [0x2018, 0x91], [0x2019, 0x92],
  [0x201c, 0x93], [0x201d, 0x94], [0x2022, 0x95], [0x2026, 0x85],
  [0x2039, 0x8b], [0x203a, 0x9b], [0x20ac, 0x80], [0x2122, 0x99],
])

function toWinAnsi(text) {
  let out = ''
  for (const character of String(text)) {
    const code = character.codePointAt(0)
    if (code < 256) out += character
    else if (WIN_ANSI.has(code)) out += String.fromCharCode(WIN_ANSI.get(code))
    else out += '?'
  }
  return out
}

export function buildPdf(imageBytes, filter, imageWidth, imageHeight, title, subtitle) {
  const chunks = []
  let length = 0
  const latin1 = (text) => {
    const out = new Uint8Array(text.length)
    for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 255
    return out
  }
  const push = (data) => {
    const bytes = typeof data === 'string' ? latin1(data) : data
    chunks.push(bytes)
    length += bytes.length
  }
  const offsets = []
  const object = (number, body) => {
    offsets[number] = length
    push(`${number} 0 obj\n`)
    push(body)
    push('\nendobj\n')
  }

  const portrait = imageHeight >= imageWidth
  const pageWidth = portrait ? A4_SHORT : A4_LONG
  const pageHeight = portrait ? A4_LONG : A4_SHORT
  const margin = 36
  const captionHeight = title ? 34 : 0
  const availableWidth = pageWidth - margin * 2
  const availableHeight = pageHeight - margin * 2 - captionHeight
  const scale = Math.min(availableWidth / imageWidth, availableHeight / imageHeight)
  const drawWidth = imageWidth * scale
  const drawHeight = imageHeight * scale
  const drawX = (pageWidth - drawWidth) / 2
  const drawY = margin + (availableHeight - drawHeight) / 2

  const escape = (text) => toWinAnsi(text).replace(/([\\()])/g, '\\$1')
  let content = ''
  if (title) {
    content += `BT /F1 14 Tf ${margin} ${(pageHeight - margin - 12).toFixed(2)} Td (${escape(title)}) Tj ET\n`
  }
  if (subtitle) {
    content += `BT /F1 9 Tf ${margin} ${(pageHeight - margin - 26).toFixed(2)} Td (${escape(subtitle)}) Tj ET\n`
  }
  content += `q ${drawWidth.toFixed(2)} 0 0 ${drawHeight.toFixed(2)} ${drawX.toFixed(2)} ${drawY.toFixed(2)} cm /Im0 Do Q`

  push('%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
  object(1, '<< /Type /Catalog /Pages 2 0 R >>')
  object(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>')
  object(3,
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth.toFixed(2)} ${pageHeight.toFixed(2)}] ` +
    '/Resources << /XObject << /Im0 4 0 R >> /Font << /F1 6 0 R >> >> /Contents 5 0 R >>')

  offsets[4] = length
  push('4 0 obj\n')
  push(
    `<< /Type /XObject /Subtype /Image /Width ${imageWidth} /Height ${imageHeight} ` +
    `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter ${filter} /Length ${imageBytes.length} >>\nstream\n`)
  push(imageBytes)
  push('\nendstream\nendobj\n')

  object(5, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`)
  object(6, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')

  const xrefOffset = length
  let xref = 'xref\n0 7\n0000000000 65535 f \n'
  for (let i = 1; i <= 6; i += 1) xref += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`
  push(xref)
  push(`trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`)

  const pdf = new Uint8Array(length)
  let position = 0
  for (const chunk of chunks) {
    pdf.set(chunk, position)
    position += chunk.length
  }
  return pdf
}

async function deflate(bytes) {
  if (typeof CompressionStream === 'undefined') return null
  try {
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('deflate'))
    return new Uint8Array(await new Response(stream).arrayBuffer())
  } catch {
    return null
  }
}

// --------------------------------------------------------------------------- //
// Public entry points
// --------------------------------------------------------------------------- //

const stamp = () => new Date().toISOString().slice(0, 10)

export async function exportPng(svg, name) {
  const canvas = await rasterize(svg, 2)
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('PNG encoding failed.')
  downloadBlob(blob, `${name}-${stamp()}.png`)
}

export async function exportGif(svg, name) {
  // GIF is palette-based, so extra resolution costs a lot for little gain.
  const canvas = await rasterize(svg, 1.5)
  const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height)
  const gif = encodeGif(data, canvas.width, canvas.height)
  downloadBlob(new Blob([gif], { type: 'image/gif' }), `${name}-${stamp()}.gif`)
}

export async function exportPdf(svg, name, title, subtitle) {
  const canvas = await rasterize(svg, 2)
  const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height)
  const rgb = new Uint8Array(canvas.width * canvas.height * 3)
  for (let i = 0, p = 0; p < rgb.length; i += 4, p += 3) {
    rgb[p] = data[i]
    rgb[p + 1] = data[i + 1]
    rgb[p + 2] = data[i + 2]
  }
  let stream = await deflate(rgb)
  let filter = '/FlateDecode'
  if (!stream) {
    // Very old engines without CompressionStream still get a valid PDF via JPEG.
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    stream = new Uint8Array(await blob.arrayBuffer())
    filter = '/DCTDecode'
  }
  const pdf = buildPdf(stream, filter, canvas.width, canvas.height, title, subtitle)
  downloadBlob(new Blob([pdf], { type: 'application/pdf' }), `${name}-${stamp()}.pdf`)
}
