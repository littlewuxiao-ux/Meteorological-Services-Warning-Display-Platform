'use strict';

function decomposeFlightEvents(flights, carriers, allowOtherCarriers, updatedAt) {
    const airports = Object.create(null);
    const selected = new Set(carriers.map(code => String(code).trim().toUpperCase()));
    const seen = new Set();
    const pickTime = (flight, fields) => {
        for (const field of fields) {
            const value = flight[field];
            if (value == null || String(value).trim() === '') continue;
            const numeric = Number(value);
            const time = Number.isFinite(numeric) ? (numeric < 100000000000 ? numeric * 1000 : numeric) : Date.parse(value);
            if (Number.isFinite(time) && time > 0) return { time, field };
        }
        return null;
    };
    for (const flight of flights) {
        if (!flight || typeof flight !== 'object') continue;
        const carrier = String(flight.carrier || '').trim().toUpperCase();
        if (!allowOtherCarriers && !selected.has(carrier)) continue;
        const dep = String(flight.departureAirport || flight.depApt || '').trim().toUpperCase();
        const arr = String(flight.arrivalAirport || flight.arrApt || '').trim().toUpperCase();
        const flightId = String(flight.flightId || flight.flightNo || '');
        const other = { flightNo: flight.flightNo || '', departureAirport: dep, arrivalAirport: arr };
        for (const [airport, role, fields] of [
            [dep, 'dep', ['atd', 'etd', 'std', 'ptd']],
            [arr, 'arr', ['ata', 'eta', 'sta', 'pta']],
        ]) {
            if (!/^[A-Z0-9]{4}$/.test(airport)) continue;
            const picked = pickTime(flight, fields);
            if (!picked) continue;
            const key = `${airport}:${flightId}:${dep}:${arr}:${role}:${picked.time}`;
            if (seen.has(key)) continue;
            seen.add(key);
            if (!airports[airport]) airports[airport] = { events: [], updated_at: updatedAt };
            airports[airport].events.push({ at: picked.time, kind: role, timeField: picked.field, carrier, flightId, other });
        }
    }
    return airports;
}

if (typeof self !== 'undefined') {
    self.onmessage = ({ data }) => {
        try {
            self.postMessage({ airports: decomposeFlightEvents(data.flights, data.carriers, data.allowOtherCarriers, data.updatedAt) });
        } catch (error) {
            self.postMessage({ error: error.message });
        }
    };
}
