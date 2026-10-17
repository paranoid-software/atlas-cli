import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {SourcesPlugster} from './sources-plugster.js';

(async function() {
    let sourcesPlugster = await new SourcesPlugster(new AtlasApi()).init();

    Plugster.plug(sourcesPlugster);
}());
