import {Plugster} from './plugster.js';

const DAY = 24 * 60 * 60 * 1000;

// Where we stand, at a glance: the KPIs, what needs attention, what closed lately.
export class OverviewPlugster extends Plugster {
    constructor(api, outlets = {
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
        $.when(this._api.get('corpus'), this._api.get('doctor')).done((corpus, doctor) => {
            this._render(corpus[0], doctor[0]);
        });
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
        let doctorCount = doctor.findings ? doctor.findings.length : 0;

        this._.kpiList.clear();
        [
            {key: 'active', filter: {place: 'active'}, name: 'Active', value: specs.filter((spec) => spec.place === 'active').length, note: '', view: 'specs'},
            {key: 'backlog', filter: {place: 'backlog'}, name: 'Backlog', value: specs.filter((spec) => spec.place === 'backlog').length, note: '', view: 'specs'},
            {key: 'closed', name: 'Closed, 7 days', value: closedLately.length, note: `${specs.filter((spec) => spec.place === 'archived').length} ${this._t('in all')}`, view: 'timeline'},
            {key: 'lead', filter: {place: 'archived'}, name: 'Median lead time', value: median === null ? '–' : `${median} d`, note: leads.length ? `${leads.length} ${this._t('SPECs')}` : '', view: 'specs'},
            {key: 'findings', filter: {findings: 'with'}, name: 'Findings', value: findings, note: '', view: 'specs'},
            {key: 'doctor', name: 'Doctor', value: doctorCount, note: doctorCount ? this._t('to fix') : this._t('all clear'), view: 'health', bad: doctorCount > 0}
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
        (doctor.findings || []).slice(0, 6).forEach((finding, index) => {
            let outlets = this._.attentionList.buildListItem(
                0, `finding-${index}`, finding, {kindLabel: {}, subjectLabel: {}}, this._.attentionList.count(),
                () => this.dispatchEvent(this.viewChosen.name, {view: 'health'}));
            outlets.kindLabel.text(finding.kind).addClass(`is-${finding.kind}`);
            outlets.subjectLabel.text(finding.detail ? `${finding.subject}: ${finding.detail}` : finding.subject);
        });
        if (!doctorCount) {
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

    toggleView(args) {
        this._.root.toggle(args.view === 'overview');
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
