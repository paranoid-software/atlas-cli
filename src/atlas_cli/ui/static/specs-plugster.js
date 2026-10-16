import {Plugster} from './plugster.js';
import MiniSearch from './minisearch.js';

// Every SPEC of the Atlas, filtered by place, repo and mode, searched in the browser.
export class SpecsPlugster extends Plugster {
    constructor(api, outlets = {
        searchInput: {},
        placeSelect: {},
        repoSelect: {},
        modeSelect: {},
        countLabel: {},
        specsList: {},
        detailPanel: {},
        detailTitle: {},
        detailMeta: {},
        detailSections: {},
        unreadableLabel: {}
    }) {
        super(outlets);
        this._api = api;
        this._specs = [];
        this._index = null;
        this._selected = null;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._.searchInput.on('input', () => this._renderList());
        this._.placeSelect.on('change', () => this._renderList());
        this._.repoSelect.on('change', () => this._renderList());
        this._.modeSelect.on('change', () => this._renderList());
        this._.detailPanel.hide();
    }

    reload() {
        this._api.get('corpus').done((corpus) => {
            this._specs = corpus.specs;
            this._index = this._buildIndex(corpus.specs);
            this._renderRepoOptions(corpus.specs);
            this._renderList();
            let unreadable = corpus.unreadable || [];
            this._.unreadableLabel.text(unreadable.length
                ? this._t('Could not read: {files}').replace('{files}', unreadable.join(', '))
                : '');
            let still = this._specs.find((spec) => spec.name === this._selected);
            if (still) this._renderDetail(still); else this._.detailPanel.hide();
        });
    }

    _buildIndex(specs) {
        let index = new MiniSearch({
            idField: 'name',
            fields: ['title', 'name', 'body', 'findings'],
            searchOptions: {boost: {title: 3, name: 2}, prefix: true, fuzzy: 0.2}
        });
        index.addAll(specs.map((spec) => ({
            name: spec.name,
            title: spec.title,
            body: Object.keys(spec.sections).map((heading) => `${heading}\n${spec.sections[heading]}`).join('\n'),
            findings: spec.findings || ''
        })));
        return index;
    }

    _renderRepoOptions(specs) {
        let chosen = this._.repoSelect.val() || '';
        let repos = [...new Set(specs.flatMap((spec) => spec.repos))].sort();
        this._.repoSelect.clear();
        [''].concat(repos).forEach((repo) => {
            let outlets = this._.repoSelect.buildListItem(
                0, `repo-${repo}`, {repo}, {option: {}}, this._.repoSelect.count());
            outlets.root.val(repo).text(repo || this._t('Every repo'));
        });
        this._.repoSelect.val(repos.includes(chosen) ? chosen : '');
    }

    _renderList() {
        let query = (this._.searchInput.val() || '').trim();
        let matches = null;
        if (query && this._index) {
            matches = new Map(this._index.search(query).map((result) => [result.id, result]));
        }
        let place = this._.placeSelect.val();
        let repo = this._.repoSelect.val();
        let mode = this._.modeSelect.val();
        let shown = this._specs.filter((spec) => {
            if (matches && !matches.has(spec.name)) return false;
            if (place && spec.place !== place) return false;
            if (repo && !spec.repos.includes(repo)) return false;
            if (mode === '(default)') return !spec.mode;
            return !mode || spec.mode === mode;
        });
        if (matches) {
            shown.sort((left, right) => matches.get(right.name).score - matches.get(left.name).score);
        } else {
            shown.sort((left, right) => right.number.localeCompare(left.number));
        }
        this._.specsList.clear();
        shown.forEach((spec) => {
            let outlets = this._.specsList.buildListItem(
                0, spec.name, spec, {nameLabel: {}, metaLabel: {}, matchLabel: {}},
                this._.specsList.count(), () => this._renderDetail(spec));
            outlets.nameLabel.text(`SPEC_${spec.number} — ${spec.title}`);
            outlets.metaLabel.text(this._meta(spec));
            let result = matches ? matches.get(spec.name) : null;
            outlets.matchLabel.text(result ? this._describeMatch(result) : '');
        });
        this._.countLabel.text(this._t('{shown} of {total} SPECs')
            .replace('{shown}', shown.length).replace('{total}', this._specs.length));
    }

    _describeMatch(result) {
        let where = Object.keys(result.match).map((term) => {
            let fields = result.match[term].map((field) => this._t(field)).join(', ');
            return `"${term}" (${fields})`;
        });
        return this._t('Matches {where}').replace('{where}', where.join(', '));
    }

    _meta(spec) {
        let parts = [this._t(spec.place)];
        if (spec.created) parts.push(this._t('created {date}').replace('{date}', spec.created));
        if (spec.started) parts.push(this._t('started {date}').replace('{date}', spec.started));
        if (spec.closed) parts.push(this._t('closed {date}').replace('{date}', spec.closed));
        if (spec.repos.length) parts.push(spec.repos.join(', '));
        parts.push(spec.mode ? spec.mode : this._t('Atlas default mode'));
        return parts.join(' · ');
    }

    _renderDetail(spec) {
        this._selected = spec.name;
        this._.detailPanel.show();
        this._.detailTitle.text(`${spec.name}`);
        this._.detailMeta.text(`${this._meta(spec)} · ${spec.file}`);
        this._.detailSections.clear();
        let blocks = Object.keys(spec.sections).map((heading) => [heading, spec.sections[heading]]);
        if (spec.findings) blocks.push([this._t('Findings'), spec.findings]);
        blocks.forEach(([heading, body], position) => {
            let outlets = this._.detailSections.buildListItem(
                0, `section-${position}`, {heading}, {headingLabel: {}, bodyText: {}},
                this._.detailSections.count());
            outlets.headingLabel.text(heading);
            outlets.bodyText.text(body);
        });
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
