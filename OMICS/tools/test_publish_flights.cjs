const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { performance } = require('node:perf_hooks');

const frontend = path.join(__dirname, '../frontend');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(frontend, 'publish_flights_worker.js'), 'utf8'), context);
const start = Date.parse('2026-10-03T01:00:00Z');
const hour = 3600000;
const flight = { carrier: 'O3', flightId: '1', flightNo: 'O3101', departureAirport: 'ZBAA', arrivalAirport: 'ZSPD',
    ptd: start, std: start + hour, etd: start + 2 * hour, atd: '', pta: start + 3 * hour, eta: start + 4 * hour };
const decompose = flights => context.decomposeFlightEvents(flights, ['O3'], false, '2026-10-03T00:00:00Z');
let airports = decompose([flight, flight, { ...flight, carrier: 'XX', flightId: '2' }]);
assert.equal(airports.ZBAA.events.length, 1);
assert.equal(airports.ZBAA.events[0].at, start + 2 * hour);
assert.equal(airports.ZSPD.events[0].at, start + 4 * hour);
airports = decompose([{ ...flight, atd: start + hour, ata: start + 5 * hour }]);
assert.equal(airports.ZBAA.events[0].at, start + hour);
assert.equal(airports.ZSPD.events[0].at, start + 5 * hour);
assert.equal(Object.keys(decompose([{ carrier: 'O3', departureAirport: 'ZBAA', ptd: null }])).length, 0);

const source = fs.readFileSync(path.join(frontend, 'publish.js'), 'utf8');
context.pbState = { startDate: '2026-10-03', startHour: 1, validityHours: 6, flightAirports: { ZBAA: { events:
    [-hour - 1, -hour, -1, 0, hour - 1, hour, 6 * hour, 6 * hour + 1, 9 * hour, 9 * hour + 1]
        .map((offset, index) => ({ at: start + offset, kind: 'dep', flightId: String(index) })) } } };
vm.runInContext(source.slice(source.indexOf('function getPublishFlightEvents('), source.indexOf('function fillPublishFlightRow(')), context);
const result = context.getPublishFlightEvents('ZBAA');
assert.equal(result.before.length, 2);
assert.equal(result.after.length, 2);
assert.equal(result.buckets[0].length, 2);
assert.equal(result.buckets[1].length, 1);
assert.equal(result.buckets[6].length, 1);

const many = Array.from({ length: 20000 }, (_, index) => ({ ...flight, flightId: String(index), etd: start + index * 1000 }));
const began = performance.now();
const large = decompose(many);
assert.equal(large.ZBAA.events.length, 20000);
console.log(`Flight priority, carrier filtering, deduplication and margin boundaries passed. 20,000 flights: ${(performance.now() - began).toFixed(0)}ms.`);
