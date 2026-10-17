import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {FlowPlugster} from './flow-plugster.js';

(async function() {
    let flowPlugster = await new FlowPlugster(new AtlasApi()).init();

    Plugster.plug(flowPlugster);
}());
