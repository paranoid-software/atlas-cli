import {Plugster} from './plugster.js';

// `atlas status`, as it prints it.
export class StatusPlugster extends Plugster {
    constructor(api, outlets = {
        statusText: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('status').done((status) => this._.statusText.text(status.text));
    }
}
