import {Plugster} from './plugster.js';

// `atlas doctor`, made plain: each source's state, and each finding with what it means and its fix.
export class DoctorPlugster extends Plugster {
    constructor(api, outlets = {
        summaryLabel: {},
        findingsHead: {},
        kindSwitch: {},
        findingsList: {}
    }) {
        super(outlets);
        this._api = api;
        this._report = null;
        this._kind = '';
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('doctor').done((report) => this._render(report));
    }

    _render(report) {
        this._report = report;
        this._.kindSwitch.clear();
        this._.findingsList.clear();
        this._.summaryLabel.removeClass('is-ok is-warn is-bad');
        this._.findingsHead.toggle(!report.error && report.findings.length > 0);
        if (report.error) {
            this._.summaryLabel.addClass('is-bad').text(report.error);
            return;
        }
        let problems = report.findings.filter((finding) => finding.level !== 'notice').length;
        let notices = report.findings.length - problems;
        if (problems) {
            let text = problems === 1 ? this._t('1 thing needs attention.') : this._t('{count} things need attention.');
            this._.summaryLabel.addClass('is-bad').text(text.replace('{count}', problems));
        } else if (notices) {
            let text = notices === 1 ? this._t('Everything is in order; 1 notice.') : this._t('Everything is in order; {count} notices.');
            this._.summaryLabel.addClass('is-warn').text(text.replace('{count}', notices));
        } else {
            this._.summaryLabel.addClass('is-ok').text(this._t('Everything is in order.'));
        }
        let kinds = [...new Set(report.findings.map((finding) => finding.kind))];
        if (!kinds.includes(this._kind)) this._kind = '';
        if (kinds.length > 1) {
            [''].concat(kinds).forEach((kind) => {
                let count = kind ? report.findings.filter((finding) => finding.kind === kind).length : report.findings.length;
                let chip = this._.kindSwitch.buildListItem(
                    0, kind || 'all', {kind}, {nameLabel: {}, countLabel: {}}, this._.kindSwitch.count(),
                    (key, data) => { this._kind = data.kind; this._render(this._report); });
                chip.nameLabel.text(kind ? this._t(kind) : this._t('All'));
                chip.countLabel.text(String(count));
                chip.root.toggleClass('is-current', kind === this._kind);
            });
        }
        report.findings.forEach((finding, index) => {
            if (!this._kind || finding.kind === this._kind) this._renderFinding(finding, index);
        });
    }

    _renderFinding(finding, index) {
        let words = this._explain(finding);
        let card = this._.findingsList.buildListItem(
            0, `finding-${index}`, finding,
            {titleLabel: {}, whyLabel: {}, detailLabel: {}, fixLabel: {}},
            this._.findingsList.count());
        card.root.toggleClass('is-notice', finding.level === 'notice');
        card.titleLabel.text(words.title);
        card.whyLabel.text(words.why);
        card.detailLabel.text(finding.detail || '');
        card.fixLabel.text(finding.fix.length ? words.fixWith : words.fixBy);
        finding.fix.forEach((command, commandIndex) => {
            let row = this._.findingsList.buildListItem(
                1, `finding-${index}-fix-${commandIndex}`, {command},
                {commandLabel: {}, copyButton: {}}, this._.findingsList.count(),
                (key, data) => this._copy(key, data.command));
            row.commandLabel.text(command);
            row.copyButton.text(this._t('Copy'));
        });
    }

    _explain(finding) {
        let subject = finding.subject;
        let nested = subject.includes('/');
        let texts = {
            missing: subject === 'CLAUDE.md' && finding.fix.length === 0 ? {
                title: 'The Atlas has no CLAUDE.md',
                why: 'Agents open this Atlas without its orientation: they don\'t know what each source is.',
                fixBy: 'Write CLAUDE.md at the Atlas root, with an orientation block per source.'
            } : {
                title: '{subject} is missing on this machine',
                why: nested
                    ? 'It is declared inside a folder of repos, but its clone is not there.'
                    : 'It is declared in the Atlas, but there is no symlink to it here, so agents can\'t read it.',
                fixWith: nested ? 'Clone it in place:' : 'Get it and link it:',
                fixBy: 'Link it to where it lives on this machine: atlas link {subject} <path>'
            },
            broken: {
                title: '{subject} points nowhere',
                why: 'Its symlink points to a path that no longer exists.',
                fixBy: 'Link it again to where it lives now: atlas link {subject} <path>'
            },
            undeclared: {
                title: '{subject} is not declared',
                why: nested
                    ? 'A repo appeared inside a folder of repos and the Atlas doesn\'t list it, so nobody else gets it.'
                    : 'A symlink the Atlas doesn\'t list: whoever clones this Atlas won\'t get it.',
                fixWith: 'Declare it:'
            },
            rules: {
                title: 'Notice: {subject} carries its own rule files',
                why: 'Tools load them on their own when working inside that source. They are its context, not this Atlas\'s rules.',
                fixBy: 'Read them with caution. Where they contradict the Atlas or the coding rules, the Atlas and the coding rules prevail, and the contradiction is a decision for the human. Nothing to fix.'
            },
            unoriented: {
                title: '{subject} has no orientation block',
                why: 'Agents don\'t know what this source is or how it is worked on.',
                fixBy: 'Write its "### {subject} — …" block in CLAUDE.md §1.'
            },
            placeholder: {
                title: '{subject}\'s orientation block is not filled in',
                why: 'It still carries the template\'s placeholders, so agents read placeholders instead of facts.',
                fixBy: 'Replace the placeholders in its block in CLAUDE.md §1.'
            },
            credentials: {
                title: '{subject}\'s remote carries credentials',
                why: 'A user or token sits in _settings/atlas.toml, a file this Atlas versions and shares.',
                fixWith: 'Rewrite it without them, then rotate the token:',
                fixBy: 'Remove the user:token@ from its remote in _settings/atlas.toml, then rotate the token.'
            }
        }[finding.kind] || {title: '{subject}: ' + finding.kind, why: '', fixBy: ''};
        let words = {};
        Object.keys(texts).forEach((key) => {
            words[key] = this._t(texts[key]).split('{subject}').join(subject);
        });
        words.fixWith = words.fixWith || this._t('Fix it with:');
        words.fixBy = words.fixBy || '';
        return words;
    }

    _copy(key, command) {
        let button = this._.findingsList.getOutlets(key).copyButton;
        window.navigator.clipboard.writeText(command).then(() => {
            button.text(this._t('Copied'));
            window.setTimeout(() => button.text(this._t('Copy')), 1500);
        }).catch(() => button.text(this._t('Select and copy it')));
    }

    toggleView(args) {
        this._.root.toggle(args.view === 'health');
    }

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
