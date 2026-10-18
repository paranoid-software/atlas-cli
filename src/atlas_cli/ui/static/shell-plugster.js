import {Plugster} from './plugster.js';

const VIEWS = [
    {id: 'overview', name: 'Overview'},
    {id: 'timeline', name: 'Timeline'},
    {id: 'health', name: 'Health'},
    {id: 'specs', name: 'SPECs'},
    {id: 'rules', name: 'Coding rules'},
    {id: 'machinery', name: 'Machinery'}
];

// The frame: the sidebar's views, which one shows, and the browser's history for it.
export class ShellPlugster extends Plugster {
    constructor(api, outlets = {
        atlasName: {},
        viewsList: {},
        versionLabel: {}
    }) {
        super(outlets);
        this._api = api;
        this._counts = {};
        this._notices = 0;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._renderViews();
        window.addEventListener('hashchange', () => this._showCurrent());
        this._showCurrent();
    }

    viewShown(data, callback) {
        this.registerEventSignature(this.viewShown.name, data, callback);
    }

    reload() {
        this._api.get('version').done((answer) => {
            if (!answer.name) return;
            this._.atlasName.text(answer.name);
            document.title = `${answer.name} · Atlas`;
        });
        this._api.get('doctor').done((report) => {
            let findings = report.findings || [];
            this._counts.health = findings.filter((finding) => finding.level !== 'notice').length;
            this._notices = findings.length - this._counts.health;
            this._renderViews();
        });
        this._api.get('corpus').done((corpus) => {
            this._counts.specs = corpus.specs.filter((spec) => spec.place === 'active').length;
            this._renderViews();
        });
        this._api.get('machinery').done((state) => {
            this._counts.machinery = state.files.filter((file) => file.state !== 'unchanged').length
                + state.hooks.filter((hook) => !hook.wired).length;
            this._renderViews();
        });
    }

    show(args) {
        this._navigate(args.view);
    }

    showSpecs() {
        this._navigate('specs');
    }

    _navigate(view) {
        if (!VIEWS.some((candidate) => candidate.id === view)) view = 'overview';
        if (window.location.hash !== `#${view}`) {
            window.location.hash = view;
        } else {
            this._showCurrent();
        }
    }

    _showCurrent() {
        let wanted = (window.location.hash || '#overview').slice(1);
        let view = VIEWS.find((candidate) => candidate.id === wanted) || VIEWS[0];
        VIEWS.forEach((candidate) => {
            let item = this._.viewsList.getOutlets(candidate.id);
            if (item) item.root.toggleClass('is-current', candidate.id === view.id);
        });
        this.dispatchEvent(this.viewShown.name, {view: view.id, name: this._t(view.name)});
    }

    _renderViews() {
        let current = (window.location.hash || '#overview').slice(1);
        this._.viewsList.clear();
        VIEWS.forEach((view) => {
            let outlets = this._.viewsList.buildListItem(
                0, view.id, view, {nameLabel: {}, countLabel: {}}, this._.viewsList.count(),
                (key) => this._navigate(key));
            outlets.root.attr('href', `#${view.id}`).toggleClass('is-current', view.id === current);
            outlets.nameLabel.text(this._t(view.name));
            let count = this._counts[view.id];
            outlets.countLabel.text(count ? String(count) : '')
                .toggleClass('is-bad', view.id !== 'specs' && count > 0)
                .toggleClass('is-active', view.id === 'specs' && count > 0);
            let title = count ? this._countTitle(view.id, count) : this._t(view.name);
            if (view.id === 'health' && this._notices) {
                title += ` · ${this._notices === 1 ? this._t('1 notice') : this._t('{count} notices').replace('{count}', this._notices)}`;
            }
            outlets.root.attr('title', title);
        });
    }

    _countTitle(view, count) {
        let titles = {
            specs: count === 1 ? '1 active SPEC' : '{count} active SPECs',
            health: count === 1 ? '1 thing to fix' : '{count} things to fix',
            machinery: count === 1 ? '1 machinery file or hook is off' : '{count} machinery files or hooks are off'
        };
        return this._t(titles[view] || '{count}').replace('{count}', count);
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
