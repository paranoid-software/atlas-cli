import {Plugster} from './plugster.js';

// The coding rules in force here: the declared source, its candidates and its deviations.
export class RulesPlugster extends Plugster {
    constructor(api, outlets = {
        sourceLabel: {},
        candidatesText: {},
        deviationsText: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('corpus').done((corpus) => {
            let rules = corpus.rules;
            this._.sourceLabel.text(rules.source
                ? this._t('Source: {source}').replace('{source}', rules.source)
                : this._t('This Atlas declares no coding-rules source.'));
            this._.candidatesText.text(rules.candidates || this._t('(none)'));
            this._.deviationsText.text(rules.deviations || this._t('(none)'));
        });
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
