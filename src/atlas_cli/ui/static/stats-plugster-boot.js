import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {StatsPlugster} from './stats-plugster.js';

(async function() {
    let statsPlugster = await new StatsPlugster(new AtlasApi()).init();

    Plugster.plug(statsPlugster);
}());
