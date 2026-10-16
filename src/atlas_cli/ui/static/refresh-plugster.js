import {Plugster} from './plugster.js';

// Watches the Atlas's files through /api/version and tells every panel when they changed.
export class RefreshPlugster extends Plugster {
    constructor(api, outlets = {
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
        window.setInterval(() => this._check(), 3000);
        window.addEventListener('focus', () => this._check());
        this._check();
    }

    atlasChanged(data, callback) {
        this.registerEventSignature(this.atlasChanged.name, data, callback);
    }

    _check() {
        this._api.get('version').done((answer) => {
            if (answer.version === this._version) return;
            this._version = answer.version;
            this._announce();
        });
    }

    _announce() {
        let time = new Date().toLocaleTimeString();
        this._.updatedLabel.text(this.translateTo(this.lang, 'Read at {time}').replace('{time}', time));
        this.dispatchEvent(this.atlasChanged.name, {version: this._version});
    }
}
