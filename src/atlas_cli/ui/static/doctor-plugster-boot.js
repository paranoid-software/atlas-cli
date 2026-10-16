import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {DoctorPlugster} from './doctor-plugster.js';

(async function() {
    let doctorPlugster = await new DoctorPlugster(new AtlasApi()).init();

    Plugster.plug(doctorPlugster);
}());
