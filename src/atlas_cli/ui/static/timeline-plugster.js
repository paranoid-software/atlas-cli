import {Plugster} from './plugster.js';

// A placeholder until the activity timeline lands (DRAFT_ATLAS_UI_V2, next SPEC).
export class TimelinePlugster extends Plugster {
    constructor(api, outlets = {
        placeholderLabel: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('timeline?days=14').done((timeline) => {
            let count = timeline.events.length;
            this._.placeholderLabel.text(
                this._t('The activity timeline comes in the next release — {count} events in the last 14 days are already waiting for it.')
                    .replace('{count}', count));
        });
    }

    toggleView(args) {
        this._.root.toggle(args.view === 'timeline');
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
