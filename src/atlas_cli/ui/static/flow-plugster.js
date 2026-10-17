import {Plugster} from './plugster.js';

const DAY = 24 * 60 * 60 * 1000;
const WEEKS = 12;
const BARS = 20;

// How work flows: SPECs started and closed per week, and how long each closed SPEC took.
export class FlowPlugster extends Plugster {
    constructor(api, outlets = {
        throughputChart: {},
        throughputNote: {},
        durationChart: {},
        durationNote: {}
    }) {
        super(outlets);
        this._api = api;
        this._specs = [];
        this._charts = [];
        this._closed = [];
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._throughput = echarts.init(this._.throughputChart[0], null, {renderer: 'canvas'});
        this._duration = echarts.init(this._.durationChart[0], null, {renderer: 'canvas'});
        this._charts = [this._throughput, this._duration];
        this._duration.on('click', (params) => {
            let spec = this._closed[params.dataIndex];
            if (spec) this.dispatchEvent(this.specChosen.name, {spec: spec.name});
        });
        window.addEventListener('resize', () => this._resize());
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => this._render());
    }

    specChosen(data, callback) {
        this.registerEventSignature(this.specChosen.name, data, callback);
    }

    reload() {
        this._api.get('corpus').done((corpus) => {
            let date = (value) => {
                let found = /^\d{4}-\d{2}-\d{2}/.exec(value || '');
                return found && !Number.isNaN(Date.parse(found[0])) ? found[0] : null;
            };
            this._specs = corpus.specs.map((spec) => ({...spec, created: date(spec.created), started: date(spec.started), closed: date(spec.closed)}));
            this._render();
        });
    }

    resize(args) {
        if (args.view === 'overview') this._resize();
    }

    _resize() {
        this._charts.forEach((chart) => chart.resize());
    }

    _colors() {
        let style = window.getComputedStyle(this._.root[0]);
        let token = (name) => style.getPropertyValue(name).trim();
        return {
            started: token('--teal'), closed: token('--ok'), lead: token('--line-strong'), working: token('--accent'),
            grid: token('--line'), text: token('--muted'), panel: token('--panel'), ink: token('--ink'), line: token('--line-strong')
        };
    }

    _render() {
        let colors = this._colors();
        this._renderThroughput(colors);
        this._renderDuration(colors);
    }

    _renderThroughput(colors) {
        let weeks = this._weeks();
        let count = (field) => weeks.map((week) => this._specs.filter((spec) => spec[field] && spec[field] >= week.from && spec[field] <= week.to).length);
        this._throughput.setOption({
            animationDuration: 300,
            grid: {left: 28, right: 8, top: 32, bottom: 24},
            legend: {top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: {color: colors.text}},
            tooltip: this._tooltip(colors),
            xAxis: {type: 'category', data: weeks.map((week) => this._short(week.from)), axisTick: {show: false},
                axisLine: {lineStyle: {color: colors.grid}}, axisLabel: {color: colors.text}},
            yAxis: {type: 'value', minInterval: 1, splitLine: {lineStyle: {color: colors.grid}}, axisLabel: {color: colors.text}},
            series: [
                {name: this._t('started'), type: 'bar', barMaxWidth: 14, itemStyle: {color: colors.started, borderRadius: [3, 3, 0, 0]}, data: count('started')},
                {name: this._t('closed'), type: 'bar', barMaxWidth: 14, itemStyle: {color: colors.closed, borderRadius: [3, 3, 0, 0]}, data: count('closed')}
            ]
        }, true);
        let parts = [this._t('Weeks start on Monday; the last one is this week.')];
        let undated = this._specs.filter((spec) => spec.place === 'archived' && !spec.closed).length;
        if (undated) parts.push(this._t('{count} archived SPECs have no closed: date.').replace('{count}', undated));
        let unstarted = this._specs.filter((spec) => !spec.started).length;
        if (unstarted) parts.push(this._t('{count} SPECs have no started: date.').replace('{count}', unstarted));
        this._.throughputNote.text(parts.join(' '));
    }

    _renderDuration(colors) {
        let closed = this._specs.filter((spec) => spec.closed && spec.created)
            .sort((left, right) => left.closed.localeCompare(right.closed) || left.number.localeCompare(right.number));
        this._closed = closed.slice(-BARS);
        let days = (from, to) => (from ? Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / DAY)) : null);
        this._duration.setOption({
            animationDuration: 300,
            grid: {left: 28, right: 8, top: 32, bottom: 24},
            legend: {top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: {color: colors.text}},
            tooltip: {...this._tooltip(colors),
                formatter: (items) => {
                    let spec = this._closed[items[0].dataIndex];
                    let lines = items.filter((item) => item.value !== null).map((item) => `${item.marker}${item.seriesName}: ${item.value} d`);
                    return [echarts.format.encodeHTML(`SPEC_${spec.number} — ${spec.title}`)].concat(lines).join('<br>');
                }},
            xAxis: {type: 'category', data: this._closed.map((spec) => spec.number), axisTick: {show: false},
                axisLine: {lineStyle: {color: colors.grid}}, axisLabel: {color: colors.text}},
            yAxis: {type: 'value', minInterval: 1, splitLine: {lineStyle: {color: colors.grid}},
                axisLabel: {color: colors.text, formatter: '{value} d'}},
            series: [
                {name: this._t('lead time'), type: 'bar', barGap: '-100%', barMaxWidth: 18, cursor: 'pointer',
                    itemStyle: {color: colors.lead, borderRadius: [3, 3, 0, 0]}, data: this._closed.map((spec) => days(spec.created, spec.closed))},
                {name: this._t('working time'), type: 'bar', barGap: '-100%', barMaxWidth: 18, cursor: 'pointer',
                    itemStyle: {color: colors.working, borderRadius: [3, 3, 0, 0]}, data: this._closed.map((spec) => days(spec.started, spec.closed))}
            ]
        }, true);
        let archived = this._specs.filter((spec) => spec.place === 'archived').length;
        let left = archived - this._specs.filter((spec) => spec.place === 'archived' && spec.closed && spec.created).length;
        let parts = [this._t('Last {count} closed SPECs; lead time from created:, working time from started:.').replace('{count}', this._closed.length)];
        let unworked = this._closed.filter((spec) => !spec.started).length;
        if (unworked) parts.push(this._t('{count} of them have no started:, so no working time.').replace('{count}', unworked));
        if (left > 0) parts.push(this._t('{count} archived SPECs lack created: or closed: and are left out.').replace('{count}', left));
        this._.durationNote.text(parts.join(' '));
    }

    _tooltip(colors) {
        return {trigger: 'axis', axisPointer: {type: 'shadow'}, backgroundColor: colors.panel, borderColor: colors.line,
            textStyle: {color: colors.ink}};
    }

    // The last WEEKS weeks, Monday to Sunday, the current one last.
    _weeks() {
        let monday = new Date();
        monday.setHours(0, 0, 0, 0);
        monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
        let weeks = [];
        for (let back = WEEKS - 1; back >= 0; back--) {
            let from = new Date(monday);
            from.setDate(from.getDate() - back * 7);
            let to = new Date(from);
            to.setDate(to.getDate() + 6);
            weeks.push({from: this._iso(from), to: this._iso(to)});
        }
        return weeks;
    }

    _iso(date) {
        return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
    }

    _short(value) {
        return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
