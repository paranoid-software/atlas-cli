import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {RulesPlugster} from './rules-plugster.js';

(async function() {
    let rulesPlugster = await new RulesPlugster(new AtlasApi()).init();

    Plugster.plug(rulesPlugster);
}());
