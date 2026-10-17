import {Plugster} from './plugster.js';

const RANGES = [
    {id: '7', name: '7d'},
    {id: '14', name: '14d'},
    {id: '30', name: '30d'},
    {id: 'all', name: 'All'}
];
const KINDS = ['created', 'started', 'commit', 'finding', 'closed'];
const COLORS = {
    light: {created: '#98a2b3', started: '#1d9e75', commit: '#2f6fdb', finding: '#7f77dd', closed: '#3b6d11', grid: '#e3e6eb', text: '#667085', today: '#161a22'},
    dark: {created: '#667085', started: '#5dcaa5', commit: '#6ea8fe', finding: '#afa9ec', closed: '#97c459', grid: '#262b34', text: '#98a2b3', today: '#e7e9ee'}
};

// What happened, day by day: a strip of days stacked by kind of event, and the feed below it.
export class TimelinePlugster extends Plugster {
    constructor(api, outlets = {
        rangeSwitch: {},
        repoSelect: {},
        summaryLabel: {},
        dayChart: {},
        emptyLabel: {},
        feedList: {}
    }) {
        super(outlets);
        this._api = api;
        this._range = '14';
        this._timeline = null;
        this._chart = null;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._chart = echarts.init(this._.dayChart[0], null, {renderer: 'canvas'});
        this._chart.on('click', (params) => this._scrollToDay(params.name));
        window.addEventListener('resize', () => this._chart.resize());
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => this._render());
        this._.repoSelect.on('change', () => this._render());
        this._renderRanges();
    }

    specChosen(data, callback) {
        this.registerEventSignature(this.specChosen.name, data, callback);
    }

    reload() {
        this._api.get(`timeline?days=${this._range}`).done((timeline) => {
            this._timeline = timeline;
            this._renderRepoOptions();
            this._render();
        });
    }

    toggleView(args) {
        this._.root.toggle(args.view === 'timeline');
        if (args.view === 'timeline' && this._chart) this._chart.resize();
    }

    _renderRanges() {
        this._.rangeSwitch.clear();
        RANGES.forEach((range) => {
            let outlets = this._.rangeSwitch.buildListItem(
                0, range.id, range, {nameLabel: {}}, this._.rangeSwitch.count(),
                (key) => { this._range = key; this._renderRanges(); this.reload(); });
            outlets.nameLabel.text(this._t(range.name));
            outlets.root.toggleClass('is-current', range.id === this._range);
        });
    }

    _renderRepoOptions() {
        let chosen = this._.repoSelect.val() || '';
        let repos = [...new Set(this._timeline.events.flatMap((event) => this._repos(event)))].sort();
        this._.repoSelect.clear();
        [''].concat(repos).forEach((repo) => {
            let outlets = this._.repoSelect.buildListItem(0, `repo-${repo}`, {repo}, {option: {}}, this._.repoSelect.count());
            outlets.root.val(repo).text(repo || this._t('Every repo'));
        });
        this._.repoSelect.val(repos.includes(chosen) ? chosen : '');
    }

    _repos(event) {
        return (event.repo || '').split(',').map((repo) => repo.trim()).filter(Boolean);
    }

    _render() {
        if (!this._timeline) return;
        let repo = this._.repoSelect.val();
        let events = this._timeline.events.filter((event) => !repo || this._repos(event).includes(repo));
        let days = this._timeline.days.map((day) => day.date);
        this._renderChart(days, events);
        this._renderFeed(events);
        let specs = new Set(events.map((event) => event.spec)).size;
        let commits = events.filter((event) => event.kind === 'commit').length;
        this._.summaryLabel.text(this._t('{events} events · {specs} SPECs · {commits} commits')
            .replace('{events}', events.length).replace('{specs}', specs).replace('{commits}', commits));
        this._.emptyLabel.text(events.length ? '' : this._t('Nothing happened in this window. Try a longer one.'));
    }

    _renderChart(days, events) {
        let colors = window.matchMedia('(prefers-color-scheme: dark)').matches ? COLORS.dark : COLORS.light;
        let today = new Date();
        let todayText = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-');
        let series = KINDS.map((kind) => ({
            name: this._t(kind),
            type: 'bar',
            stack: 'events',
            barMaxWidth: 28,
            itemStyle: {color: colors[kind], borderRadius: kind === 'closed' ? [3, 3, 0, 0] : 0},
            emphasis: {focus: 'series'},
            data: days.map((day) => events.filter((event) => event.date === day && event.kind === kind).length)
        }));
        this._chart.setOption({
            animationDuration: 300,
            grid: {left: 32, right: 12, top: 36, bottom: 28},
            legend: {top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: {color: colors.text}},
            tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}},
            xAxis: {
                type: 'category',
                data: days,
                axisTick: {show: false},
                axisLine: {lineStyle: {color: colors.grid}},
                axisLabel: {
                    color: colors.text,
                    formatter: (value) => this._shortDate(value, value === todayText),
                    rich: {today: {color: colors.today, fontWeight: 'bold'}}
                }
            },
            yAxis: {type: 'value', minInterval: 1, splitLine: {lineStyle: {color: colors.grid}}, axisLabel: {color: colors.text}},
            series
        }, true);
    }

    _shortDate(value, isToday) {
        let date = new Date(`${value}T00:00:00`);
        let text = date.toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
        return isToday ? `{today|${this._t('Today')}}` : text;
    }

    _renderFeed(events) {
        this._.feedList.clear();
        let byDay = new Map();
        events.forEach((event) => {
            if (!byDay.has(event.date)) byDay.set(event.date, []);
            byDay.get(event.date).push(event);
        });
        [...byDay.keys()].sort().reverse().forEach((date) => {
            let dayEvents = byDay.get(date);
            let day = this._.feedList.buildListItem(
                0, `day-${date}`, {date}, {dateLabel: {}, countLabel: {}}, this._.feedList.count());
            day.dateLabel.text(new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {weekday: 'long', month: 'long', day: 'numeric'}));
            day.countLabel.text(dayEvents.length === 1 ? this._t('1 event') : this._t('{count} events').replace('{count}', dayEvents.length));
            dayEvents.forEach((event, index) => {
                let row = this._.feedList.buildListItem(
                    1, `event-${date}-${index}`, event,
                    {dot: {}, kindLabel: {}, specLabel: {}, detailLabel: {}, repoLabel: {}}, this._.feedList.count(),
                    (key, data) => this.dispatchEvent(this.specChosen.name, {spec: data.spec}));
                row.dot.addClass(`is-${event.kind}`);
                row.kindLabel.text(this._t(event.kind)).addClass(`is-${event.kind}`);
                row.specLabel.text(event.title ? `${event.spec.slice(0, 9)} — ${event.title}` : event.spec);
                row.detailLabel.text(event.detail || '');
                row.repoLabel.text(event.repo || '');
            });
        });
    }

    _scrollToDay(date) {
        let day = this._.feedList.getOutlets(`day-${date}`);
        if (day) day.root[0].scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
