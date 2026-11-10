import { Component, input } from '@angular/core';

export type IconName =
  | 'alert-circle'
  | 'bag'
  | 'ban'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'check'
  | 'circle-check'
  | 'close'
  | 'dashboard'
  | 'download'
  | 'eye'
  | 'eye-off'
  | 'file-code'
  | 'file-spreadsheet'
  | 'file-text'
  | 'filter'
  | 'history'
  | 'inbox'
  | 'key'
  | 'layers'
  | 'log-out'
  | 'lock'
  | 'mail'
  | 'map-pin'
  | 'message-circle'
  | 'menu'
  | 'mic'
  | 'monitor-smartphone'
  | 'refresh'
  | 'search'
  | 'shield'
  | 'sparkles'
  | 'phone'
  | 'pencil'
  | 'plus'
  | 'store'
  | 'table'
  | 'trending-up'
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
