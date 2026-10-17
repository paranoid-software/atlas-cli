import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {TimelinePlugster} from './timeline-plugster.js';

(async function() {
    let timelinePlugster = await new TimelinePlugster(new AtlasApi()).init();

    Plugster.plug(timelinePlugster);
}());
