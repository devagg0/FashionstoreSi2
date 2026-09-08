import { Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-promotion-detail-shell',
  template: '<ng-content />',
  styleUrl: './promotion-detail-shell.scss',
  encapsulation: ViewEncapsulation.None,
})
export class PromotionDetailShell {}
