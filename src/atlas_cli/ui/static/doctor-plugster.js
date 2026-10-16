import {Plugster} from './plugster.js';

// `atlas doctor`, made plain: each source's state, and each finding with what it means and its fix.
export class DoctorPlugster extends Plugster {
    constructor(api, outlets = {
        summaryLabel: {},
        sourcesList: {},
        findingsList: {}
    }) {
        super(outlets);
        this._api = api;
        this.setLocales({});
    }

    afterInit() {
        this.lang = this._.root.data('lang');
    }

    reload() {
        this._api.get('doctor').done((report) => this._render(report));
    }

    _render(report) {
        this._.sourcesList.clear();
        this._.findingsList.clear();
        this._.summaryLabel.removeClass('is-ok is-bad');
        if (report.error) {
            this._.summaryLabel.addClass('is-bad').text(report.error);
            return;
        }
        report.sources.forEach((source) => this._renderSource(source));
        report.findings.forEach((finding, index) => this._renderFinding(finding, index));
        if (report.ok) {
            this._.summaryLabel.addClass('is-ok').text(this._t('Everything is in order.'));
        } else {
            let count = report.findings.length;
            let text = count === 1 ? this._t('1 thing needs attention.') : this._t('{count} things need attention.');
            this._.summaryLabel.addClass('is-bad').text(text.replace('{count}', count));
        }
    }

    _renderSource(source) {
        let outlets = this._.sourcesList.buildListItem(
            0, source.name, source, {nameLabel: {}, stateLabel: {}}, this._.sourcesList.count());
        let missingRepos = (source.repos || []).filter((repo) => repo.state !== 'ok').length;
        let healthy = source.state === 'ok' && missingRepos === 0;
        outlets.root.addClass(healthy ? 'is-ok' : 'is-bad');
        outlets.nameLabel.text(source.name);
        let state = this._t(source.state);
        if (source.repos) {
            let present = source.repos.length - missingRepos;
            state = this._t('{state}, {present} of {total} repos')
                .replace('{state}', state).replace('{present}', present).replace('{total}', source.repos.length);
        }
        outlets.stateLabel.text(state);
    }

    _renderFinding(finding, index) {
        let words = this._explain(finding);
        let card = this._.findingsList.buildListItem(
            0, `finding-${index}`, finding,
            {titleLabel: {}, whyLabel: {}, detailLabel: {}, fixLabel: {}},
            this._.findingsList.count());
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
                title: '{subject} carries agent rule files',
                why: 'Rule files inside a source leak into every Atlas that links it.',
                fixBy: 'Move what they say into this Atlas\'s CLAUDE.md and remove them from the source.'
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

    _t(text) {
        return this.translateTo(this.lang, text);
    }
}
