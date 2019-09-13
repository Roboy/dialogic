import {Injectable} from "@angular/core";
import {Observable, Subject} from "rxjs";
import {filter, map} from "rxjs/operators";
import {ActivationUpdate, SpikeUpdate} from "../model/model";
import * as io from "socket.io-client";


@Injectable({
    providedIn: 'root'
})
export class SocketIOService {

    dataStream: Subject<SpikeUpdate | ActivationUpdate>;

    activations: Observable<ActivationUpdate>;
    spikes: Observable<SpikeUpdate>;

    constructor() {
        this.dataStream = new Subject();
        this.activations = this.dataStream.pipe(filter(data => data.type === 'activation'), map(data => data as ActivationUpdate));
        this.spikes = this.dataStream.pipe(filter(data => data.type === 'spike'), map( data => data as SpikeUpdate));

        let socket = io.connect("http://localhost:4242");
        let scope = this;

        socket.on('spike', msg => {
            scope.dataStream.next(msg)
        });

        socket.on('activation', msg => {
            scope.dataStream.next(msg)
        });
    }
}