import { Component, Input } from '@angular/core';

export enum NodeType {
    ACTIVATION,
    SPIKE
}

@Component({
    selector: '[node]',
    template: `
        <svg:circle *ngIf="!rectangular" [ngClass]="shapeClass" 
                    [attr.cx]="x" [attr.cy]="y" [attr.r]="circleRadius"/>
        <svg:rect *ngIf="rectangular" [ngClass]="shapeClass" 
                  [attr.x]="x - rectWidth / 2" [attr.y]="y - rectHeight / 2"
                  [attr.width]="rectWidth" [attr.height]="rectHeight" [attr.rx]="rectCornerRounding"/>
        <svg:text class="node-label" text-anchor="middle"
                  [attr.x]="x" [attr.y]="y+4" >{{label}}</svg:text>
    `,
    styleUrls: ['./styles.scss']
})
export class NodeComponent {

    // shape params
    readonly rectWidth = 120;
    readonly rectHeight = 40;
    readonly rectCornerRounding = 5;
    readonly circleRadius = 30;

    @Input() x: number = 0;
    @Input() y: number = 0;
    @Input() label: string = 'state';
    @Input() nodeType: NodeType = NodeType.ACTIVATION;
    @Input() nodeStatus: string = null;  // null for spike;  'wait' | 'ready' | 'run' for activation

    get rectangular(): boolean {
        return true; // this.nodeType == NodeType.ACTIVATION;
    };

    get shapeClass(): string {
        let cls = this.nodeType == NodeType.ACTIVATION ? 'activation-node' : 'spike-node';
        if (this.nodeStatus) {
            cls += ' ' + this.nodeStatus;
        }
        return cls;
    }
}
