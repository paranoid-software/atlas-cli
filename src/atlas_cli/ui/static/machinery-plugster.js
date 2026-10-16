import {Plugster} from './plugster.js';

// What `atlas setup claude` installed: each file against the package, each hook wired or not.
export class MachineryPlugster extends Plugster {
    constructor(api, outlets = {
        folderLabel: {},
        machineryList: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('machinery').done((state) => this._render(state));
    }

    _render(state) {
        let folder = this._t('In {folder}').replace('{folder}', state.folder);
        if (state.error) folder = `${folder} — ${state.error}`;
        this._.folderLabel.text(folder);
        this._.machineryList.clear();
        state.files.forEach((file) => {
            this._row(`file-${file.name}`, file.name, this._t(file.state), file.state === 'unchanged');
        });
        state.hooks.forEach((hook) => {
            let name = this._t('{event} hook ({script})').replace('{event}', hook.event).replace('{script}', hook.script);
            this._row(`hook-${hook.event}`, name, this._t(hook.wired ? 'wired' : 'not wired'), hook.wired);
        });
    }

    _row(key, name, state, healthy) {
        let outlets = this._.machineryList.buildListItem(
            0, key, {}, {nameLabel: {}, stateLabel: {}}, this._.machineryList.count());
        outlets.nameLabel.text(name);
        outlets.stateLabel.text(state).addClass(healthy ? 'is-ok' : 'is-bad');
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
