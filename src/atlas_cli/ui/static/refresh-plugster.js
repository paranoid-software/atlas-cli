import {Plugster} from './plugster.js';

// The header: the current view's title, the Atlas's health, the search box, and the watch on
// /api/version that tells every view when the Atlas's files changed.
export class RefreshPlugster extends Plugster {
    constructor(api, outlets = {
        viewTitle: {},
        healthBadge: {},
        searchButton: {},
        updatedLabel: {},
        reloadButton: {}
    }) {
        super(outlets);
        this._api = api;
        this._version = null;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
        this._.reloadButton.click(() => this._announce());
        this._.searchButton.click(() => this.dispatchEvent(this.searchRequested.name, {from: 'header'}));
        window.setInterval(() => this._check(), 3000);
        window.addEventListener('focus', () => this._check());
        this._check();
    }

    atlasChanged(data, callback) {
        this.registerEventSignature(this.atlasChanged.name, data, callback);
    }

    searchRequested(data, callback) {
        this.registerEventSignature(this.searchRequested.name, data, callback);
    }

    setTitle(args) {
        this._.viewTitle.text(args.name);
    }

    _check() {
        this._api.get('version').done((answer) => {
            if (answer.version === this._version) return;
            this._version = answer.version;
            this._announce();
        });
    }

    _announce() {
        let time = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
        this._.updatedLabel.text(this.translateTo(this.lang, 'Read at {time}').replace('{time}', time));
        this._api.get('doctor').done((report) => this._badge(report));
        this.dispatchEvent(this.atlasChanged.name, {version: this._version});
    }

    _badge(report) {
        this._.healthBadge.removeClass('is-ok is-bad');
        if (report.error) {
            this._.healthBadge.addClass('is-bad').text(this.translateTo(this.lang, 'not an Atlas'));
            return;
        }
        let count = report.findings.length;
        if (!count) {
            this._.healthBadge.addClass('is-ok').text(this.translateTo(this.lang, 'healthy'));
            return;
        }
        let text = count === 1 ? this.translateTo(this.lang, '1 thing needs attention') : this.translateTo(this.lang, '{count} things need attention');
        this._.healthBadge.addClass('is-bad').text(text.replace('{count}', count));
    }
}
