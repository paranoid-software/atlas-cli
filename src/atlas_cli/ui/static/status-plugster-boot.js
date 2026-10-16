import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {StatusPlugster} from './status-plugster.js';

(async function() {
    let statusPlugster = await new StatusPlugster(new AtlasApi()).init();

    Plugster.plug(statusPlugster);
}());
