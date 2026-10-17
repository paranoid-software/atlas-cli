import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {OverviewPlugster} from './overview-plugster.js';

(async function() {
    let overviewPlugster = await new OverviewPlugster(new AtlasApi()).init();

    Plugster.plug(overviewPlugster);
}());
