import {Plugster} from './plugster.js';

// The source map: one card per source and nested repo, with where its git stands right now.
export class SourcesPlugster extends Plugster {
    constructor(api, outlets = {
        summaryLabel: {},
        sourcesList: {},
        unreadableLabel: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('sources').done((payload) => this._render(payload));
    }

    _render(payload) {
        this._.sourcesList.clear();
        if (payload.error) {
            this._.summaryLabel.text(payload.error);
            this._.unreadableLabel.text('');
            return;
        }
        let sources = payload.sources || [];
        sources.forEach((source) => this._renderSource(source));
        let repos = sources.filter((source) => source.kind === 'repo');
        let dirty = repos.filter((source) => source.changes > 0).length;
        let onSpec = repos.filter((source) => (source.branch || '').startsWith('spec/')).length;
        this._.summaryLabel.text(this._t('{repos} repos · {dirty} with uncommitted changes · {spec} on a spec branch')
            .replace('{repos}', repos.length).replace('{dirty}', dirty).replace('{spec}', onSpec));
        let unreadable = payload.unreadable || [];
        this._.unreadableLabel.text(unreadable.length
            ? this._t('Could not read the git of: {names}').replace('{names}', unreadable.join(', '))
            : '');
    }

    _renderSource(source) {
        let card = this._.sourcesList.buildListItem(
            0, source.name, source,
            {nameLabel: {}, stateLabel: {}, kindLabel: {}, gitRow: {}, branchLabel: {}, changesLabel: {}, lastLabel: {}, specBranchesLabel: {}},
            this._.sourcesList.count());
        let nested = source.name.includes('/');
        card.root.addClass(`is-${this._tone(source)}`).toggleClass('is-nested', nested);
        card.nameLabel.text(source.name);
        card.stateLabel.text(this._t(source.state)).addClass(`is-${source.state}`);
        card.kindLabel.text(this._t({repo: 'git repo', folder: 'folder of repos', plain: 'no git'}[source.kind] || source.kind || ''));
        card.gitRow.toggle(source.kind === 'repo');
        card.branchLabel.text(source.branch || '').toggle(Boolean(source.branch))
            .toggleClass('is-spec', (source.branch || '').startsWith('spec/'));
        card.changesLabel.text(this._changes(source)).toggle(source.kind === 'repo')
            .toggleClass('is-dirty', source.changes > 0);
        card.lastLabel.text(source.last
            ? `${source.last.date} · ${source.last.author} · ${source.last.subject}`
            : (source.kind === 'repo' ? this._t('No commits yet') : ''));
        let branches = source.spec_branches || [];
        card.specBranchesLabel.text(branches.length
            ? this._t('Spec branches: {branches}').replace('{branches}', branches.map((entry) => `${entry.branch} (${entry.last})`).join(', '))
            : '');
    }

    // Git changes without the Atlas's files changing: read again each time Health is shown.
    refresh(args) {
        if (args.view === 'health') this.reload();
    }

    _tone(source) {
        if (source.state !== 'ok') return 'bad';
        if (source.changes > 0) return 'warn';
        return 'ok';
    }

    _changes(source) {
        if (!source.changes) return this._t('clean');
        return source.changes === 1 ? this._t('1 change') : this._t('{count} changes').replace('{count}', source.changes);
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
