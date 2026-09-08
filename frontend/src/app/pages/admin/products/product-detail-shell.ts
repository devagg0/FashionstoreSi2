import { Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-product-detail-shell',
  template: '<ng-content />',
  styleUrl: './product-detail-shell.scss',
  encapsulation: ViewEncapsulation.None,
})
export class ProductDetailShell {}
