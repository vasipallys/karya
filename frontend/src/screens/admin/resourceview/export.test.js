import { describe, expect, it } from 'vitest'
import { buildPdf, encodeGif, lzwEncode, quantize } from './export'

const latin1 = (bytes) => {
  let out = ''
  for (const byte of bytes) out += String.fromCharCode(byte)
  return out
}

/** Reference GIF-LZW decoder, used to prove lzwEncode round-trips. */
function lzwDecode(bytes, minCodeSize) {
  const clearCode = 1 << minCodeSize
  const endCode = clearCode + 1
  let dict = []
  let codeSize = minCodeSize + 1
  const reset = () => {
    dict = []
    for (let i = 0; i < clearCode; i += 1) dict.push([i])
    dict.push(null, null) // clear + end placeholders
    codeSize = minCodeSize + 1
  }
  reset()

  const out = []
  let acc = 0
  let accBits = 0
  let pos = 0
  let previous = null

  const read = () => {
    while (accBits < codeSize) {
      if (pos >= bytes.length) return null
      acc |= bytes[pos] << accBits
      pos += 1
      accBits += 8
    }
    const code = acc & ((1 << codeSize) - 1)
    acc >>>= codeSize
    accBits -= codeSize
    return code
  }

  for (;;) {
    const code = read()
    if (code === null || code === endCode) break
    if (code === clearCode) { reset(); previous = null; continue }
    let entry
    if (code < dict.length && dict[code]) entry = dict[code]
    else entry = [...previous, previous[0]]
    out.push(...entry)
    if (previous) {
      dict.push([...previous, entry[0]])
      if (dict.length > (1 << codeSize) - 1 && codeSize < 12) codeSize += 1
    }
    previous = entry
  }
  return out
}

describe('lzwEncode', () => {
  it('round-trips a flat run', () => {
    const indices = new Uint8Array(500).fill(7)
    expect(lzwDecode(lzwEncode(indices, 8), 8)).toEqual([...indices])
  })

  it('round-trips repeating structure that grows the dictionary', () => {
    const indices = new Uint8Array(4000)
    for (let i = 0; i < indices.length; i += 1) indices[i] = (i * i) % 13
    expect(lzwDecode(lzwEncode(indices, 8), 8)).toEqual([...indices])
  })

  it('round-trips pseudo-random data past a code-width increase', () => {
    let seed = 42
    const indices = new Uint8Array(9000)
    for (let i = 0; i < indices.length; i += 1) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff
      indices[i] = seed % 200
    }
    expect(lzwDecode(lzwEncode(indices, 8), 8)).toEqual([...indices])
  })
})

describe('quantize', () => {
  it('keeps colours exactly when there are fewer than 256', () => {
    const width = 2
    const height = 2
    const data = new Uint8ClampedArray([
      255, 0, 0, 255, 0, 255, 0, 255,
      0, 0, 255, 255, 255, 0, 0, 255,
    ])
    const { indices, palette } = quantize(data, width, height)
    expect(palette).toHaveLength(3)
    // First and last pixels are the same red, so they share a palette slot.
    expect(indices[0]).toBe(indices[3])
    expect(palette[indices[0]]).toBe(0xff0000)
    expect(palette[indices[1]]).toBe(0x00ff00)
    expect(palette[indices[2]]).toBe(0x0000ff)
  })
})

describe('encodeGif', () => {
  it('emits a structurally valid GIF89a', () => {
    const width = 8
    const height = 8
    const data = new Uint8ClampedArray(width * height * 4)
    for (let p = 0; p < width * height; p += 1) {
      const i = p * 4
      data[i] = p % 2 ? 255 : 20
      data[i + 1] = 60
      data[i + 2] = 120
      data[i + 3] = 255
    }
    const gif = encodeGif(data, width, height)
    expect(latin1(gif.slice(0, 6))).toBe('GIF89a')
    // Logical screen descriptor carries the dimensions, little-endian.
    expect(gif[6] | (gif[7] << 8)).toBe(width)
    expect(gif[8] | (gif[9] << 8)).toBe(height)
    expect(gif[10] & 0x80).toBe(0x80) // global colour table present
    expect(gif[gif.length - 1]).toBe(0x3b) // trailer
    expect(gif[gif.length - 2]).toBe(0x00) // block terminator
    expect(gif).toContain(0x2c) // image descriptor
  })
})

describe('buildPdf', () => {
  const image = new Uint8Array(64).fill(200)
  const pdf = buildPdf(image, '/FlateDecode', 4, 4, 'Karya — Resource view', 'subtitle line')
  const text = latin1(pdf)

  it('starts with a PDF header and ends with EOF', () => {
    expect(text.startsWith('%PDF-1.4')).toBe(true)
    expect(text.endsWith('%%EOF\n')).toBe(true)
  })

  it('writes an xref whose offsets land exactly on their objects', () => {
    const startxref = text.match(/startxref\n(\d+)\n%%EOF\n$/)
    expect(startxref).not.toBeNull()
    const xrefOffset = Number(startxref[1])
    expect(text.slice(xrefOffset, xrefOffset + 4)).toBe('xref')

    const entries = [...text.slice(xrefOffset).matchAll(/(\d{10}) 00000 n /g)].map((m) => Number(m[1]))
    expect(entries).toHaveLength(6)
    entries.forEach((offset, index) => {
      const marker = `${index + 1} 0 obj`
      expect(text.slice(offset, offset + marker.length)).toBe(marker)
    })
  })

  it('declares the image stream length that it actually writes', () => {
    const match = text.match(/\/Filter \/FlateDecode \/Length (\d+) >>\nstream\n/)
    expect(match).not.toBeNull()
    expect(Number(match[1])).toBe(image.length)
    const streamStart = match.index + match[0].length
    expect(text.slice(streamStart + image.length, streamStart + image.length + 11)).toBe('\nendstream\n')
  })

  it('escapes parentheses in the caption so the content stream stays valid', () => {
    const risky = buildPdf(image, '/FlateDecode', 4, 4, 'Report (final) \\ v2', '')
    expect(latin1(risky)).toContain('(Report \\(final\\) \\\\ v2) Tj')
  })

  it('re-encodes typography to WinAnsi instead of truncating code points', () => {
    const fancy = buildPdf(image, '/FlateDecode', 4, 4, 'Karya — view · “x” … 😀', '')
    const out = latin1(fancy)
    expect(out).toContain('(Karya \x97 view \xb7 \x93x\x94 \x85 ?) Tj')
    expect(out).not.toContain('\x14') // the em dash must not become a control byte
  })

  it('declares a content length matching the bytes written', () => {
    const doc = buildPdf(image, '/FlateDecode', 4, 4, 'Title — dash', 'sub')
    const out = latin1(doc)
    const match = out.match(/<< \/Length (\d+) >>\nstream\n([\s\S]*?)\nendstream/)
    expect(match).not.toBeNull()
    expect(match[2].length).toBe(Number(match[1]))
  })
})
