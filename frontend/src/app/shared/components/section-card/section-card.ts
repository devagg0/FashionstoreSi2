import { Component, input } from '@angular/core';

@Component({
  selector: 'app-section-card',
  templateUrl: './section-card.html',
  styleUrl: './section-card.scss',
})
export class SectionCard {
  readonly title = input.required<string>();
  readonly image = input.required<string>();
  readonly alt = input.required<string>();
  readonly position = input('center');
}
