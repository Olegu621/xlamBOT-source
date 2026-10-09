const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/setup-entry.js'), 'utf8');

async function visit(devices, stored = {}) {
    const elements = new Map();
    let dialogs = 0;
    const requests = [];
    const document = {
        documentElement: {lang: 'en'},
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, {
                hidden: true, textContent: '',
                setAttribute() {}, addEventListener() {},
                showModal() { dialogs++; },
            });
            return elements.get(id);
        },
    };
    const context = {
        document, window: {addEventListener() {}},
        localStorage: {
            getItem: name => stored[name] || null,
            setItem: (name, value) => { stored[name] = value; },
        },
        XlamSession: { async fetch(url, options) {
            requests.push({url, options});
            return {ok: true, json: async () => ({devices})};
        } },
    };
    await vm.runInNewContext(source, context);
    return {elements, dialogs, requests, stored};
}

test('a first idle visit offers setup without starting a device', async () => {
    const result = await visit([{runtime: {state: 'idle', is_running: false}}]);
    assert.equal(result.dialogs, 1);
    assert.equal(result.elements.get('setupEntry').hidden, false);
    assert.deepEqual(result.requests, [{url: '/api/devices', options: undefined}]);
});

for (const state of ['running', 'paused', 'pausing', 'starting', 'stopping']) {
    test(`setup does not interrupt a ${state} device`, async () => {
        const result = await visit([{runtime: {state, is_running: state === 'running'}}]);
        assert.equal(result.dialogs, 0);
        assert.equal(result.requests.length, 1);
    });
}

test('a finished guide stays out of the way on later visits', async () => {
    const result = await visit([], {'xlam-setup-complete': '1'});
    assert.equal(result.dialogs, 0);
    assert.equal(result.elements.get('setupEntry').hidden, true);
    assert.equal(result.requests.length, 0);
});
