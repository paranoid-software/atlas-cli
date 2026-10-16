import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {RefreshPlugster} from './refresh-plugster.js';

(async function() {
    let refreshPlugster = await new RefreshPlugster(new AtlasApi()).init();

    Plugster.plug(refreshPlugster);
}());
