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
        this._.healthBadge.removeClass('is-ok is-warn is-bad');
        if (report.error) {
            this._.healthBadge.addClass('is-bad').text(this.translateTo(this.lang, 'not an Atlas'));
            return;
        }
        let problems = report.findings.filter((finding) => finding.level !== 'notice').length;
        let notices = report.findings.length - problems;
        if (problems) {
            let text = problems === 1 ? this.translateTo(this.lang, '1 thing to fix') : this.translateTo(this.lang, '{count} things to fix');
            this._.healthBadge.addClass('is-bad').text(text.replace('{count}', problems));
        } else if (notices) {
            let text = notices === 1 ? this.translateTo(this.lang, 'healthy, 1 notice') : this.translateTo(this.lang, 'healthy, {count} notices');
            this._.healthBadge.addClass('is-warn').text(text.replace('{count}', notices));
        } else {
            this._.healthBadge.addClass('is-ok').text(this.translateTo(this.lang, 'healthy'));
        }
    }
}
