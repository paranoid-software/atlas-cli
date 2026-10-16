import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {SpecsPlugster} from './specs-plugster.js';

(async function() {
    let specsPlugster = await new SpecsPlugster(new AtlasApi()).init();

    Plugster.plug(specsPlugster);
}());
