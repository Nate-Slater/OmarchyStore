.pragma library

var CATALOG_URL = "https://plugins.omarchy.org/catalog.json"
var MAX_CATALOG_ENTRIES = 20000
var MAX_CATALOG_BYTES = 24 * 1024 * 1024

function safeText(value, maxLength) {
  if (typeof value !== "string") return ""
  return value.slice(0, maxLength || 500).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ")
}

function validPluginId(value) {
  var id = String(value || "")
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id)
    && id.indexOf("..") < 0
    && id.indexOf("omarchy.") !== 0
}

// Never execute the marketplace's installCommand. Accept only a plain GitHub
// owner/repository URL, then construct the git URL used by Omarchy ourselves.
function repository(value) {
  var text = String(value || "")
  var match = /^https:\/\/github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)\/([A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?)(?:\.git)?\/?$/.exec(text)
  if (!match || match[2].indexOf("..") >= 0) return ""
  return "https://github.com/" + match[1] + "/" + match[2].replace(/\.git$/, "") + ".git"
}

function normalizePlugin(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  if (raw.sourceType !== "community" || raw.placeholder === true) return null
  var id = String(raw.id || "")
  var name = safeText(raw.name, 120)
  var repo = repository(raw.repo)
  if (!validPluginId(id) || !name || !repo) return null

  var tags = []
  if (Array.isArray(raw.tags)) {
    for (var i = 0; i < raw.tags.length && tags.length < 16; i++) {
      var tag = safeText(raw.tags[i], 40)
      if (tag) tags.push(tag)
    }
  }

  var upstreamStatus = safeText(raw.upstreamCheckStatus, 40)
  var layout = safeText(raw.repositoryLayout, 40)
  return {
    id: id,
    name: name,
    description: safeText(raw.description, 1200),
    author: safeText(raw.author, 100) || "Unknown",
    version: safeText(raw.version, 64) || "Unknown",
    category: safeText(raw.category, 80) || "Other",
    kind: safeText(raw.kind, 80),
    tags: tags,
    repo: repo,
    license: safeText(raw.license, 80) || "Unknown",
    verificationStatus: safeText(raw.verificationStatus, 40) || "unverified",
    verificationCoverage: safeText(raw.verificationCoverage, 40),
    verificationMethod: safeText(raw.verificationMethod, 60),
    installNote: safeText(raw.installNote, 500),
    upstreamStatus: upstreamStatus,
    installAvailable: raw.installAvailable === true
      && upstreamStatus !== "failed"
      && layout === "root-plugin"
  }
}

function normalizeCatalog(data) {
  if (!data || typeof data !== "object" || !Array.isArray(data.plugins))
    throw new Error("The marketplace response is not a plugin catalog")
  if (data.plugins.length > MAX_CATALOG_ENTRIES)
    throw new Error("The marketplace catalog is larger than the supported limit")

  var seen = Object.create(null)
  var plugins = []
  for (var i = 0; i < data.plugins.length; i++) {
    var plugin = normalizePlugin(data.plugins[i])
    if (!plugin || seen[plugin.id]) continue
    seen[plugin.id] = true
    plugins.push(plugin)
  }
  plugins.sort(function(a, b) {
    if (a.installAvailable !== b.installAvailable) return a.installAvailable ? -1 : 1
    return a.name.localeCompare(b.name)
  })
  return {
    plugins: plugins,
    generatedAt: safeText(data.generatedAt, 40)
  }
}

function searchPlugins(plugins, query) {
  var text = String(query || "").toLowerCase().replace(/^\s+|\s+$/g, "")
  if (!text) return (plugins || []).slice(0)
  var terms = text.split(/\s+/)
  var out = []
  var list = plugins || []
  for (var i = 0; i < list.length; i++) {
    var plugin = list[i]
    var haystack = [plugin.name, plugin.id, plugin.author, plugin.description,
      plugin.category, plugin.kind, plugin.tags.join(" ")].join(" ").toLowerCase()
    var matches = true
    for (var t = 0; t < terms.length; t++) {
      if (haystack.indexOf(terms[t]) < 0) {
        matches = false
        break
      }
    }
    if (matches) out.push(plugin)
  }
  return out
}

function installedMap(raw) {
  var rows
  try { rows = JSON.parse(String(raw || "")) } catch (e) { return null }
  if (!Array.isArray(rows)) return null
  var out = Object.create(null)
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i]
    if (!row || !validPluginId(row.id)) continue
    out[row.id] = { enabled: row.enabled === true, firstParty: row.firstParty === true }
  }
  return out
}

function installArgs(plugin) {
  if (!plugin || !plugin.installAvailable || !validPluginId(plugin.id)) return []
  var url = repository(plugin.repo)
  return url ? ["plugin", "add", url, "--enable", "--yes"] : []
}

function enableArgs(plugin) {
  if (!plugin || !validPluginId(plugin.id)) return []
  return ["plugin", "enable", plugin.id]
}

function removeArgs(plugin) {
  if (!plugin || !validPluginId(plugin.id)) return []
  return ["plugin", "remove", plugin.id, "--yes"]
}
