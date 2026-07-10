const { contextBridge } = require('electron')

function readArgument(name) {
  const prefix = `--${name}=`
  const match = process.argv.find((item) => item.startsWith(prefix))
  return match ? match.slice(prefix.length) : ''
}

contextBridge.exposeInMainWorld('storyPointer', Object.freeze({
  apiBaseUrl: readArgument('storypointer-api-base') || 'http://localhost:8000',
  mode: 'electron',
  platform: process.platform,
}))
