import {Plugster} from './plugster.js';
import MiniSearch from './minisearch.js';

const VIEWS = [
    {id: 'overview', name: 'Overview'},
    {id: 'timeline', name: 'Timeline'},
    {id: 'health', name: 'Health'},
    {id: 'specs', name: 'SPECs'},
    {id: 'rules', name: 'Coding rules'},
    {id: 'machinery', name: 'Machinery'}
];

// ⌘K: one box that jumps to a view, a SPEC, a finding, a candidate or a deviation.
export class PalettePlugster extends Plugster {
    constructor(api, outlets = {
        paletteBox: {},
        queryInput: {},
        resultsList: {}
    }) {
        super(outlets);
        this._api = api;
        this._index = null;
        this._entries = [];
        this._shown = [];
        this._cursor = 0;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._.root.removeClass('is-open');
        this._.root.on('click', (event) => {
            if (event.target === this._.root[0]) this._close();
        });
        this._.queryInput.on('input', () => this._search());
        this._.queryInput.on('keydown', (event) => this._key(event));
        window.addEventListener('keydown', (event) => {
            let key = (event.key || '').toLowerCase();
            if ((event.metaKey || event.ctrlKey) && key === 'k') {
                event.preventDefault();
                this.open();
            } else if (key === 'escape' && this._.root.hasClass('is-open')) {
                this._close();
            }
        });
    }

    viewChosen(data, callback) {
        this.registerEventSignature(this.viewChosen.name, data, callback);
    }

    specChosen(data, callback) {
        this.registerEventSignature(this.specChosen.name, data, callback);
    }

    reload() {
        this._api.get('corpus').done((corpus) => this._buildIndex(corpus));
    }

    open() {
        this._.root.addClass('is-open');
        this._.queryInput.val('').trigger('focus');
        this._search();
    }

    _close() {
        this._.root.removeClass('is-open');
    }

    _buildIndex(corpus) {
        this._entries = VIEWS.map((view) => ({
            id: `view:${view.id}`, kind: 'view', title: this._t(view.name), text: '', numbers: '', hint: '',
            view: view.id, spec: null
        }));
        corpus.specs.forEach((spec) => {
            let body = Object.keys(spec.sections).map((heading) => spec.sections[heading]).join('\n');
            this._entries.push({
                id: `spec:${spec.name}`, kind: 'spec', title: `SPEC_${spec.number} — ${spec.title}`, text: body,
                numbers: `${spec.number} ${Number(spec.number)}`, hint: this._t(spec.place), view: 'specs', spec: spec.name
            });
            (spec.findings || '').split('\n').filter((line) => line.startsWith('- ')).forEach((line, index) => {
                this._entries.push({
                    id: `finding:${spec.name}:${index}`, kind: 'finding', title: this._headline(line.slice(2)), text: line,
                    numbers: '', hint: `SPEC_${spec.number}`, view: 'specs', spec: spec.name
                });
            });
        });
        this._rules(corpus.rules.candidates, 'candidate');
        this._rules(corpus.rules.deviations, 'deviation');
        this._index = new MiniSearch({
            idField: 'id',
            fields: ['title', 'text', 'numbers'],
            storeFields: ['id'],
            searchOptions: {boost: {numbers: 4, title: 3}, prefix: true, fuzzy: (term) => (term.length > 3 ? 0.2 : 0)}
        });
        this._index.addAll(this._entries);
    }

    _rules(text, kind) {
        if (!text) return;
        text.split('\n').filter((line) => line.startsWith('- **')).forEach((line, index) => {
            this._entries.push({
                id: `${kind}:${index}`, kind, title: this._headline(line.slice(2)), text: line,
                numbers: '', hint: '', view: 'rules', spec: null
            });
        });
    }

    _headline(text) {
        text = text.trim();
        if (text.startsWith('**')) {
            let end = text.indexOf('**', 2);
            if (end > 2) {
                let inside = text.slice(2, end).replace(/:$/, '');
                let rest = text.slice(end + 2).trim();
                return rest && inside.length < 24 ? `${inside} ${rest}`.slice(0, 120) : inside;
            }
        }
        return text.slice(0, 120);
    }

    _search() {
        let query = (this._.queryInput.val() || '').trim();
        let byId = new Map(this._entries.map((entry) => [entry.id, entry]));
        if (!query || !this._index) {
            this._shown = this._entries.filter((entry) => entry.kind === 'view');
        } else {
            this._shown = this._index.search(query).slice(0, 12).map((result) => byId.get(result.id));
        }
        this._cursor = 0;
        this._renderResults();
    }

    _renderResults() {
        this._.resultsList.clear();
        this._shown.forEach((entry, index) => {
            let outlets = this._.resultsList.buildListItem(
                0, entry.id, entry, {kindLabel: {}, titleLabel: {}, hintLabel: {}}, this._.resultsList.count(),
                (key, data) => this._choose(data));
            outlets.kindLabel.text(this._t(entry.kind)).addClass(`is-${entry.kind}`);
            outlets.titleLabel.text(entry.title);
            outlets.hintLabel.text(entry.hint);
            outlets.root.toggleClass('is-cursor', index === this._cursor);
        });
    }

    _key(event) {
        if (event.key === 'Escape') { this._close(); return; }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            let step = event.key === 'ArrowDown' ? 1 : -1;
            this._cursor = Math.max(0, Math.min(this._shown.length - 1, this._cursor + step));
            this._shown.forEach((entry, index) => {
                let outlets = this._.resultsList.getOutlets(entry.id);
                if (outlets) outlets.root.toggleClass('is-cursor', index === this._cursor);
            });
            return;
        }
        if (event.key === 'Enter' && this._shown[this._cursor]) {
            this._choose(this._shown[this._cursor]);
        }
    }

    _choose(entry) {
        this._close();
        if (entry.spec) {
            this.dispatchEvent(this.specChosen.name, {spec: entry.spec});
        } else {
            this.dispatchEvent(this.viewChosen.name, {view: entry.view});
        }
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
