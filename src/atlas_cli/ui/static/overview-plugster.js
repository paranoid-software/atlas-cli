import {Plugster} from './plugster.js';

const DAY = 24 * 60 * 60 * 1000;

// Where we stand, at a glance: the KPIs, what needs attention, what closed lately.
export class OverviewPlugster extends Plugster {
    constructor(api, outlets = {
        flightCard: {},
        flightTitle: {},
        flightList: {},
        kpiList: {},
        attentionList: {},
        recentList: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    viewChosen(data, callback) {
        this.registerEventSignature(this.viewChosen.name, data, callback);
    }

    specChosen(data, callback) {
        this.registerEventSignature(this.specChosen.name, data, callback);
    }

    reload() {
        $.when(this._api.get('corpus'), this._api.get('doctor'), this._api.get('sources')).done((corpus, doctor, sources) => {
            this._renderFlight(corpus[0].specs, sources[0].sources || []);
            this._render(corpus[0], doctor[0]);
        });
    }

    _renderFlight(specs, sources) {
        let active = specs.filter((spec) => spec.place === 'active').sort((left, right) => left.number.localeCompare(right.number));
        this._.flightList.clear();
        this._.flightTitle.text(active.length
            ? this._t('In flight · {count}').replace('{count}', active.length)
            : this._t('In flight'));
        if (!active.length) {
            let outlets = this._.flightList.buildListItem(
                0, 'none', {}, {statusLabel: {}, nameLabel: {}, ageLabel: {}, nextLabel: {}, reposLabel: {}}, 0);
            outlets.statusLabel.hide();
            outlets.nameLabel.text(this._t('Nothing in flight.'));
            outlets.nextLabel.text(this._t('The backlog says what comes next.'));
            return;
        }
        let byName = new Map(sources.map((source) => [source.name, source]));
        active.forEach((spec) => {
            let outlets = this._.flightList.buildListItem(
                0, spec.name, spec, {statusLabel: {}, nameLabel: {}, ageLabel: {}, nextLabel: {}, reposLabel: {}},
                this._.flightList.count(), (key) => this.dispatchEvent(this.specChosen.name, {spec: key}));
            outlets.statusLabel.text(spec.status || this._t('active'));
            outlets.nameLabel.text(`SPEC_${spec.number} — ${spec.title}`);
            outlets.ageLabel.text(this._age(spec));
            let next = spec.handoff && (spec.handoff.Blocked || spec.handoff.Next);
            outlets.nextLabel.text(next ? `${spec.handoff.Blocked ? this._t('Blocked') : this._t('Next')}: ${next}` : '');
            outlets.nextLabel.toggleClass('is-blocked', Boolean(spec.handoff && spec.handoff.Blocked));
            outlets.reposLabel.text(spec.repos.map((repo) => this._repoState(repo, spec.number, byName)).join('   ·   '));
        });
    }

    _age(spec) {
        let since = spec.started || spec.created;
        if (!since) return '';
        let days = Math.max(0, Math.round((Date.now() - Date.parse(`${since}T00:00:00`)) / DAY));
        let label = spec.started ? this._t('started') : this._t('created');
        if (days === 0) return `${label} ${this._t('today')}`;
        return `${label} ${days === 1 ? this._t('yesterday') : this._t('{days} days ago').replace('{days}', days)}`;
    }

    _repoState(repo, number, byName) {
        let source = byName.get(repo);
        if (!source || source.branch === null) return repo;
        let onBranch = source.branch.startsWith(`spec/${number}-`);
        let where = onBranch ? this._t('on its branch') : this._t('on {branch}').replace('{branch}', source.branch);
        let changes = source.changes ? this._t('{count} changed').replace('{count}', source.changes) : this._t('clean');
        return `${repo}: ${where}, ${changes}`;
    }

    _render(corpus, doctor) {
        let specs = corpus.specs;
        let weekStart = new Date();
        weekStart.setDate(weekStart.getDate() - 6);
        let weekAgo = [weekStart.getFullYear(), String(weekStart.getMonth() + 1).padStart(2, '0'), String(weekStart.getDate()).padStart(2, '0')].join('-');
        let closedLately = specs.filter((spec) => spec.closed && spec.closed >= weekAgo);
        let leads = specs
            .filter((spec) => spec.created && spec.closed)
            .map((spec) => Math.round((Date.parse(spec.closed) - Date.parse(spec.created)) / DAY))
            .filter((days) => !Number.isNaN(days) && days >= 0)
            .sort((left, right) => left - right);
        let median = leads.length ? (leads.length % 2 ? leads[(leads.length - 1) / 2] : (leads[leads.length / 2 - 1] + leads[leads.length / 2]) / 2) : null;
        let findings = specs.reduce((sum, spec) => sum + (spec.findings || '').split('\n').filter((line) => line.startsWith('- ')).length, 0);
        let doctorFindings = doctor.findings || [];
        let doctorCount = doctorFindings.filter((finding) => finding.level !== 'notice').length;
        let noticeCount = doctorFindings.length - doctorCount;

        this._.kpiList.clear();
        [
            {key: 'active', filter: {place: 'active'}, name: 'Active', value: specs.filter((spec) => spec.place === 'active').length, note: '', view: 'specs'},
            {key: 'backlog', filter: {place: 'backlog'}, name: 'Backlog', value: specs.filter((spec) => spec.place === 'backlog').length, note: '', view: 'specs'},
            {key: 'closed', name: 'Closed, 7 days', value: closedLately.length, note: `${specs.filter((spec) => spec.place === 'archived').length} ${this._t('in all')}`, view: 'timeline'},
            {key: 'lead', filter: {place: 'archived'}, name: 'Median lead time', value: median === null ? '–' : `${median} d`, note: leads.length ? `${leads.length} ${this._t('SPECs')}` : '', view: 'specs'},
            {key: 'findings', filter: {findings: 'with'}, name: 'Findings', value: findings, note: '', view: 'specs'},
            {key: 'doctor', name: 'Doctor', value: doctorCount, view: 'health', bad: doctorCount > 0,
                note: doctorCount ? this._t('to fix') : (noticeCount ? (noticeCount === 1 ? this._t('1 notice') : this._t('{count} notices').replace('{count}', noticeCount)) : this._t('all clear'))}
        ].forEach((kpi) => {
            let outlets = this._.kpiList.buildListItem(
                0, kpi.key, kpi, {nameLabel: {}, valueLabel: {}, noteLabel: {}}, this._.kpiList.count(),
                (key, data) => this.dispatchEvent(this.viewChosen.name, {view: data.view, filter: data.filter || null}));
            outlets.root.attr('href', `#${kpi.view}`).toggleClass('is-bad', Boolean(kpi.bad));
            outlets.nameLabel.text(this._t(kpi.name));
            outlets.valueLabel.text(String(kpi.value));
            outlets.noteLabel.text(kpi.note);
        });

        this._.attentionList.clear();
        doctorFindings.slice(0, 6).forEach((finding, index) => {
            let outlets = this._.attentionList.buildListItem(
                0, `finding-${index}`, finding, {kindLabel: {}, subjectLabel: {}}, this._.attentionList.count(),
                () => this.dispatchEvent(this.viewChosen.name, {view: 'health'}));
            let notice = finding.level === 'notice';
            outlets.kindLabel.text(notice ? this._t('notice') : finding.kind).addClass(notice ? 'is-notice' : `is-${finding.kind}`);
            outlets.subjectLabel.text(notice
                ? this._t('{subject} carries its own rule files: {files}').replace('{subject}', finding.subject).replace('{files}', finding.detail || '')
                : (finding.detail ? `${finding.subject}: ${finding.detail}` : finding.subject));
        });
        this._dataNotes(specs, corpus.unrecognized || []).forEach((note) => {
            let outlets = this._.attentionList.buildListItem(
                0, `data-${note.key}`, note, {kindLabel: {}, subjectLabel: {}}, this._.attentionList.count(),
                (key, data) => this.dispatchEvent(this.viewChosen.name, {view: 'specs', filter: data.filter}));
            outlets.kindLabel.text(this._t('data')).addClass('is-data');
            outlets.subjectLabel.text(note.text);
            outlets.root.attr('title', note.title);
        });
        if (!this._.attentionList.count()) {
            let outlets = this._.attentionList.buildListItem(
                0, 'clear', {}, {kindLabel: {}, subjectLabel: {}}, 0);
            outlets.kindLabel.text(this._t('ok')).addClass('is-ok');
            outlets.subjectLabel.text(this._t('Everything is in order.'));
        }

        this._.recentList.clear();
        specs.filter((spec) => spec.closed).sort((left, right) => right.closed.localeCompare(left.closed) || right.number.localeCompare(left.number))
            .slice(0, 8).forEach((spec) => {
                let outlets = this._.recentList.buildListItem(
                    0, spec.name, spec, {nameLabel: {}, whenLabel: {}}, this._.recentList.count(),
                    (key) => this.dispatchEvent(this.specChosen.name, {spec: key}));
                outlets.nameLabel.text(`SPEC_${spec.number} — ${spec.title}`);
                outlets.whenLabel.text(spec.closed);
            });
    }

    // What the page cannot show because the Atlas's files predate it: said, never fixed.
    _dataNotes(specs, unrecognized) {
        let notes = [];
        let unclosed = specs.filter((spec) => spec.place === 'archived' && !spec.closed).length;
        if (unclosed) {
            notes.push({
                key: 'closed', filter: {place: 'archived'},
                text: this._t('{count} archived SPECs have no closed: date').replace('{count}', unclosed),
                title: this._t('They are listed and searchable, but stay out of lead time, the timeline and Recently closed.')
            });
        }
        let undated = specs.filter((spec) => !spec.created).length;
        if (undated) {
            notes.push({
                key: 'created', filter: null,
                text: this._t('{count} SPECs have no created: date').replace('{count}', undated),
                title: this._t('They are listed and searchable, but have no created event in the timeline.')
            });
        }
        if (unrecognized.length) {
            notes.push({
                key: 'names', filter: null,
                text: this._t('Not shown, not named SPEC_NNNN_SLUG.md: {files}').replace('{files}', unrecognized.join(', ')),
                title: unrecognized.join('\n')
            });
        }
        return notes;
    }

    toggleView(args) {
        this._.root.toggle(args.view === 'overview');
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
