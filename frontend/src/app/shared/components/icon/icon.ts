import { Component, input } from '@angular/core';

export type IconName =
  | 'bag'
  | 'ban'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'check'
  | 'circle-check'
  | 'close'
  | 'dashboard'
  | 'eye'
  | 'eye-off'
  | 'filter'
  | 'key'
  | 'log-out'
  | 'lock'
  | 'mail'
  | 'map-pin'
  | 'menu'
  | 'monitor-smartphone'
  | 'refresh'
  | 'search'
  | 'shield'
  | 'phone'
  | 'pencil'
  | 'plus'
  | 'store'
  | 'user'
  | 'user-plus'
  | 'users';

@Component({
  selector: 'app-icon',
  templateUrl: './icon.html',
  styleUrl: './icon.scss',
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(20);
}
