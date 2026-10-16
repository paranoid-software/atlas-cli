import {Plugster} from './plugster.js';

const DAY = 24 * 60 * 60 * 1000;

// How the work has gone, from the SPEC files alone: their stamps, findings, modes and repos.
export class StatsPlugster extends Plugster {
    constructor(api, outlets = {
        durationsLabel: {},
        weeksChart: {},
        findingsChart: {},
        modesChart: {},
        reposChart: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('corpus').done((corpus) => this._render(corpus.specs));
    }

    _render(specs) {
        this._.durationsLabel.text(this._durations(specs));
        this._chart(this._.weeksChart, this._closedPerWeek(specs));
        this._chart(this._.findingsChart, this._findingsPerSpec(specs));
        this._chart(this._.modesChart, this._count(specs.map((spec) => spec.mode || this._t('Atlas default'))));
        this._chart(this._.reposChart, this._count(specs.flatMap((spec) => spec.repos)));
    }

    _durations(specs) {
        let lead = this._days(specs, 'created', 'closed');
        let working = this._days(specs, 'started', 'closed');
        if (!lead.length && !working.length) return this._t('No SPEC carries the stamps to measure time yet.');
        let parts = [];
        if (lead.length) parts.push(this._describe(this._t('Lead time (created → closed)'), lead));
        if (working.length) parts.push(this._describe(this._t('Working time (started → closed)'), working));
        return parts.join(' ');
    }

    _days(specs, from, to) {
        return specs
            .filter((spec) => spec[from] && spec[to])
            .map((spec) => Math.round((Date.parse(spec[to]) - Date.parse(spec[from])) / DAY))
            .filter((days) => !Number.isNaN(days) && days >= 0);
    }

    _describe(label, days) {
        let sorted = [...days].sort((left, right) => left - right);
        let middle = Math.floor(sorted.length / 2);
        let median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
        let average = days.reduce((sum, value) => sum + value, 0) / days.length;
        return this._t('{label}: median {median} days, average {average}, longest {longest}, over {count} SPECs.')
            .replace('{label}', label).replace('{median}', median).replace('{average}', average.toFixed(1))
            .replace('{longest}', sorted[sorted.length - 1]).replace('{count}', days.length);
    }

    _closedPerWeek(specs) {
        let weeks = this._count(specs.filter((spec) => spec.closed).map((spec) => this._week(spec.closed)));
        return weeks.sort((left, right) => left[0].localeCompare(right[0]));
    }

    _week(date) {
        let day = new Date(`${date}T00:00:00Z`);
        let weekday = day.getUTCDay() || 7;
        day.setUTCDate(day.getUTCDate() + 4 - weekday);
        let yearStart = new Date(Date.UTC(day.getUTCFullYear(), 0, 1));
        let week = Math.ceil(((day - yearStart) / DAY + 1) / 7);
        return `${day.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
    }

    _findingsPerSpec(specs) {
        return specs
            .map((spec) => [`SPEC_${spec.number}`, (spec.findings || '').split('\n').filter((line) => line.startsWith('- ')).length])
            .filter(([, count]) => count > 0)
            .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
            .slice(0, 12);
    }

    _count(values) {
        let counts = new Map();
        values.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));
        return [...counts.entries()].sort((left, right) => right[1] - left[1] || String(left[0]).localeCompare(String(right[0])));
    }

    _chart(outlet, rows) {
        outlet.clear();
        let largest = Math.max(1, ...rows.map(([, value]) => value));
        rows.forEach(([name, value]) => {
            let bar = outlet.buildListItem(
                0, `bar-${name}`, {name, value}, {nameLabel: {}, barFill: {}, valueLabel: {}}, outlet.count());
            bar.nameLabel.text(name).attr('title', name);
            bar.barFill.css('width', `${(value / largest) * 100}%`);
            bar.valueLabel.text(value);
        });
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
