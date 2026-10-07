const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

test('a roster arriving after the first device poll replaces the empty placeholder', async () => {
  const source = readFileSync(join(__dirname, '../static/js/panel.js'), 'utf8');
  const start = source.indexOf('    let brawlerCatalog = []');
  const end = source.indexOf('    async function applyLockedBrawler(', start);
  assert.ok(start >= 0 && end > start);
  let html = '', renders = 0;
  const container = {dataset: {}, get innerHTML() {return html;},
    set innerHTML(value) {html = value; renders++;}};
  const title = {textContent: ''};
  const context = vm.createContext({
    grid: {querySelector: selector => selector.includes('data-brawler-grid') ? container : title},
    api: async () => ({data: {brawlers: [{name: 'shelly', icon_url: '/shelly.png'}]}}),
    cssEscape: value => value, escapeHtml: value => value, liveByKey: {},
  });
  vm.runInContext(source.slice(start, end) + '\nthis.load = loadBrawlers; this.render = renderBrawlerGrid;', context);
  context.render('emulator-5554');
  assert.match(html, /Каталог бойцов недоступен/);
  await context.load();
  context.render('emulator-5554');
  assert.match(html, /data-action="lock-brawler"/);
  assert.match(html, /Shelly/);
  assert.doesNotMatch(html, /Каталог бойцов недоступен/);
  context.render('emulator-5554');
  assert.equal(renders, 2, 'unchanged device polls should preserve the rendered roster');
});
