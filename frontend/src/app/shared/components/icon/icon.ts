import { Component, input } from '@angular/core';

export type IconName =
  | 'bag'
  | 'chevron-down'
  | 'chevron-right'
  | 'check'
  | 'close'
  | 'eye'
  | 'eye-off'
  | 'lock'
  | 'mail'
  | 'map-pin'
  | 'menu'
  | 'monitor-smartphone'
  | 'phone'
  | 'store'
  | 'user';

@Component({
  selector: 'app-icon',
  templateUrl: './icon.html',
  styleUrl: './icon.scss',
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(20);
}
