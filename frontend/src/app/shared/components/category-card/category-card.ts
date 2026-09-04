import { Component, input } from '@angular/core';
import { Icon } from '../icon/icon';

@Component({
  selector: 'app-category-card',
  imports: [Icon],
  templateUrl: './category-card.html',
  styleUrl: './category-card.scss',
})
export class CategoryCard {
  readonly label = input.required<string>();
  readonly index = input.required<number>();
}
