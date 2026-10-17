import {Plugster} from './plugster.js';
import MiniSearch from './minisearch.js';

const FILTER_NAMES = {
    active: 'active SPECs',
    backlog: 'SPECs in the backlog',
    archived: 'archived SPECs',
    unplaced: 'unplaced SPECs',
    with: 'SPECs with findings'
};

// Every SPEC of the Atlas: filtered by place, repo, mode and findings, searched in the browser
// with the matches highlighted, one of them open in the reading pane.
export class SpecsPlugster extends Plugster {
    constructor(api, outlets = {
        searchInput: {},
        placeSelect: {},
        repoSelect: {},
        modeSelect: {},
        findingsSelect: {},
        filterBar: {},
        filterLabel: {},
        clearFilterButton: {},
        clearAllButton: {},
        countLabel: {},
        specsList: {},
        detailPanel: {},
        detailEmpty: {},
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
        this._terms = [];
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._.searchInput.on('input', () => this._renderList());
        [this._.placeSelect, this._.repoSelect, this._.modeSelect, this._.findingsSelect].forEach((select) => {
            select.on('change', () => this._renderList());
        });
        this._.clearFilterButton.click(() => this._clearFilters());
        this._.clearAllButton.click(() => this._clearFilters());
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
            this._renderSelected();
        });
    }

    open(args) {
        this._selected = args.spec;
        this._renderSelected();
    }

    _toggle(name) {
        this._selected = this._selected === name ? null : name;
        this._renderSelected();
    }

    applyFilter(args) {
        if (args.view !== 'specs' || !args.filter) return;
        this._.searchInput.val('');
        this._.placeSelect.val(args.filter.place || '');
        this._.findingsSelect.val(args.filter.findings || '');
        this._.repoSelect.val('');
        this._.modeSelect.val('');
        this._renderList();
    }

    toggleView(args) {
        this._.root.toggle(args.view === 'specs');
    }

    _clearFilters() {
        this._.searchInput.val('');
        [this._.placeSelect, this._.repoSelect, this._.modeSelect, this._.findingsSelect].forEach((select) => select.val(''));
        this._renderList();
    }

    _buildIndex(specs) {
        let index = new MiniSearch({
            idField: 'name',
            fields: ['title', 'name', 'numbers', 'body', 'findings'],
            searchOptions: {boost: {numbers: 4, title: 3, name: 2}, prefix: true, fuzzy: (term) => (term.length > 3 ? 0.2 : 0)}
        });
        index.addAll(specs.map((spec) => ({
            name: spec.name,
            title: spec.title,
            numbers: `${spec.number} ${Number(spec.number)}`,
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
        this._terms = [];
        if (query && this._index) {
            let results = this._index.search(query);
            matches = new Map(results.map((result) => [result.id, result]));
            let terms = new Set(query.toLowerCase().split(/\s+/).filter((word) => word.length > 1));
            results.forEach((result) => result.terms.forEach((term) => terms.add(term)));
            this._terms = [...terms];
        }
        let place = this._.placeSelect.val();
        let repo = this._.repoSelect.val();
        let mode = this._.modeSelect.val();
        let findings = this._.findingsSelect.val();
        let shown = this._specs.filter((spec) => {
            if (matches && !matches.has(spec.name)) return false;
            if (place && spec.place !== place) return false;
            if (repo && !spec.repos.includes(repo)) return false;
            if (findings === 'with' && !spec.findings) return false;
            if (mode === '(default)') return !spec.mode;
            return !mode || spec.mode === mode;
        });
        let activeFirst = (left, right) => (right.place === 'active') - (left.place === 'active');
        if (matches) {
            shown.sort((left, right) => activeFirst(left, right) || matches.get(right.name).score - matches.get(left.name).score);
        } else {
            shown.sort((left, right) => activeFirst(left, right) || right.number.localeCompare(left.number));
        }
        this._.specsList.clear();
        shown.forEach((spec) => {
            let outlets = this._.specsList.buildListItem(
                0, spec.name, spec, {statusLabel: {}, nameLabel: {}, metaLabel: {}, matchLabel: {}},
                this._.specsList.count(), (key) => this._toggle(key));
            let active = spec.place === 'active';
            outlets.root.toggleClass('is-active', active);
            outlets.statusLabel.toggle(active).text(active ? (spec.status || this._t('active')) : '');
            this._highlight(outlets.nameLabel, `SPEC_${spec.number} — ${spec.title}`);
            outlets.metaLabel.text(this._meta(spec));
            let result = matches ? matches.get(spec.name) : null;
            outlets.matchLabel.text(result ? this._describeMatch(result) : '');
        });
        this._.countLabel.text(this._t('{shown} of {total} SPECs')
            .replace('{shown}', shown.length).replace('{total}', this._specs.length));
        this._renderFilterBar(query, place, repo, mode, findings);
        if (this._selected) this._renderSelected();
    }

    _renderFilterBar(query, place, repo, mode, findings) {
        let parts = [];
        if (place) parts.push(this._t(FILTER_NAMES[place]));
        if (findings) parts.push(this._t(FILTER_NAMES[findings]));
        if (repo) parts.push(this._t('in {repo}').replace('{repo}', repo));
        if (mode) parts.push(mode === '(default)' ? this._t('in the Atlas default mode') : this._t('in {mode} mode').replace('{mode}', mode));
        if (query) parts.push(this._t('matching "{query}"').replace('{query}', query));
        this._.filterBar.toggleClass('is-filtered', parts.length > 0);
        this._.clearAllButton.toggleClass('is-armed', parts.length > 0);
        this._.clearFilterButton.toggle(parts.length > 0);
        this._.filterLabel.text(parts.length
            ? this._t('Showing: {filters}').replace('{filters}', parts.join(' · '))
            : this._t('Showing: every SPEC'));
    }

    _describeMatch(result) {
        let where = Object.keys(result.match).map((term) => {
            let fields = result.match[term].filter((field) => field !== 'numbers').map((field) => this._t(field)).join(', ');
            return fields ? `"${term}" (${fields})` : `"${term}"`;
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

    _renderSelected() {
        let spec = this._specs.find((candidate) => candidate.name === this._selected);
        if (!spec) {
            this._.detailPanel.hide();
            this._.detailEmpty.show();
            this._markSelected(false);
            return;
        }
        this._.detailEmpty.hide();
        this._.detailPanel.show();
        this._highlight(this._.detailTitle, `SPEC_${spec.number} — ${spec.title}`);
        this._.detailMeta.text(`${this._meta(spec)} · ${spec.file}`);
        this._.detailSections.clear();
        let blocks = Object.keys(spec.sections).map((heading) => [heading, spec.sections[heading]]);
        if (spec.findings) blocks.push([this._t('Findings'), spec.findings]);
        blocks.forEach(([heading, body], position) => {
            let outlets = this._.detailSections.buildListItem(
                0, `section-${position}`, {heading}, {headingLabel: {}, bodyText: {}},
                this._.detailSections.count());
            outlets.headingLabel.text(heading);
            this._highlight(outlets.bodyText, body);
        });
        this._markSelected(true);
    }

    _markSelected(scroll) {
        this._.specsList.getItemsAsArray().forEach((item) => {
            let selected = item.outlets.root.attr('data-key') === this._selected;
            item.outlets.root.toggleClass('is-selected', selected).attr('aria-selected', selected ? 'true' : 'false');
            if (selected && scroll) this._scrollListTo(item.outlets.root[0]);
        });
    }

    _scrollListTo(row) {
        let list = this._.specsList[0];
        let top = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
        if (top < list.scrollTop) list.scrollTop = top;
        else if (top + row.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + row.offsetHeight - list.clientHeight;
    }

    _highlight(outlet, text) {
        outlet.empty();
        if (!this._terms.length) {
            outlet.text(text);
            return;
        }
        let pattern = new RegExp(`(${this._terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
        text.split(pattern).forEach((part, index) => {
            if (!part) return;
            outlet.append(index % 2 === 1 ? $('<mark>').text(part) : document.createTextNode(part));
        });
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
