import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {MachineryPlugster} from './machinery-plugster.js';

(async function() {
    let machineryPlugster = await new MachineryPlugster(new AtlasApi()).init();

    Plugster.plug(machineryPlugster);
}());
